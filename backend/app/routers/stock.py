"""Item catalogue, inventory movement ledger, purchases and PDF/CSV imports."""
import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from .. import inventory as inv
from .. import ledger, parsing
from ..config import get_settings
from ..core import admin_user, audit, current_user, err, money, norm_name, parse_date, qty, today_ist
from ..db import get_db
from ..models import (
    Expense, ImportBatch, ImportRow, InventoryMovement, Item, ItemAlias, ItemSaleLine, PurchaseBill, PurchaseLine, User, Vendor, utcnow,
)

router = APIRouter()
ZERO = Decimal("0")


# ------------------------------------------------------------------ items
def item_out(db, it: Item, with_stock=False):
    d = {"id": it.id, "name": it.name, "category": it.category, "department": it.department, "kind": it.kind,
         "base_unit": it.base_unit, "sell_unit": it.sell_unit, "purchase_unit": it.purchase_unit,
         "purchase_to_base": it.purchase_to_base, "sell_to_base": it.sell_to_base, "track_stock": it.track_stock,
         "low_stock_threshold": it.low_stock_threshold, "pending": it.pending, "uom_hint": it.uom_hint,
         "source_name": it.source_name, "source_report": it.source_report, "active": it.active,
         "aliases": [a.alias for a in db.query(ItemAlias).filter(ItemAlias.item_id == it.id)]}
    if with_stock:
        d["stock"] = inv.stock_view(db, it)
    return d


@router.get("/items")
def items(q: str = "", pending: Optional[bool] = None, tracked: Optional[bool] = None, db: Session = Depends(get_db),
          _: User = Depends(current_user)):
    qs = db.query(Item).order_by(Item.name)
    if q:
        qs = qs.filter(Item.name.ilike(f"%{q}%"))
    if pending is not None:
        qs = qs.filter(Item.pending.is_(pending))
    if tracked is not None:
        qs = qs.filter(Item.track_stock.is_(tracked))
    return [item_out(db, i) for i in qs.limit(2000)]


def _apply_item_fields(it: Item, body: dict):
    for k in ("category", "department", "base_unit", "sell_unit", "purchase_unit", "uom_hint"):
        if k in body:
            setattr(it, k, str(body[k] or "").strip())
    if "kind" in body:
        if body["kind"] not in ("product", "prepared_dish"):
            err(422, "kind must be product or prepared_dish")
        it.kind = body["kind"]
    for k in ("purchase_to_base", "sell_to_base", "low_stock_threshold"):
        if k in body:
            it.__setattr__(k, None if body[k] in (None, "") else qty(body[k], k))
    for k in ("track_stock", "pending", "active"):
        if k in body:
            setattr(it, k, bool(body[k]))
    if it.purchase_unit and it.purchase_unit.lower() != (it.base_unit or "").lower() and it.purchase_to_base is None:
        err(422, "Enter the purchase-to-base conversion factor (e.g. 1 case = 12 Nos) — it is never guessed from the name")


@router.post("/items")
def add_item(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    it = inv.create_item(db, user, body.get("name", ""), source_report="manual", pending=False)
    _apply_item_fields(it, body)
    db.commit()
    return item_out(db, it, True)


@router.patch("/items/{iid}")
def edit_item(iid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    it = db.get(Item, iid)
    if not it:
        err(404, "Item not found")
    before = item_out(db, it)
    if body.get("name") and body["name"].strip() != it.name:
        n = norm_name(body["name"])
        other = db.query(Item).filter(Item.norm_name == n, Item.id != it.id).first()
        if other:
            err(409, f"Another item is already named '{other.name}'")
        it.name, it.norm_name = body["name"].strip(), n
    _apply_item_fields(it, body)
    if "pending" not in body and ("track_stock" in body or "name" in body):
        it.pending = False
    audit(db, user, "update", "item", it.id, before=before, after=body)
    db.commit()
    return item_out(db, it, True)


@router.post("/items/{iid}/aliases")
def add_alias(iid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    it = db.get(Item, iid)
    if not it:
        err(404, "Item not found")
    inv.add_alias(db, user, it, body.get("alias", ""), body.get("source_report", "manual"))
    db.commit()
    return item_out(db, it)


# ------------------------------------------------------------------ inventory
@router.get("/inventory/stock")
def stock(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [inv.stock_view(db, i) for i in db.query(Item).filter(Item.track_stock.is_(True), Item.active.is_(True)).order_by(Item.name)]


@router.get("/inventory/movements")
def movements(item_id: Optional[int] = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = db.query(InventoryMovement).order_by(InventoryMovement.business_date.desc(), InventoryMovement.id.desc())
    if item_id:
        q = q.filter(InventoryMovement.item_id == item_id)
    return [{"id": m.id, "item_id": m.item_id, "item": m.item.name, "business_date": m.business_date.isoformat(),
             "movement_type": m.movement_type, "quantity": m.quantity, "source_type": m.source_type,
             "source_id": m.source_id, "import_batch_id": m.import_batch_id, "reason": m.reason} for m in q.limit(1000)]


@router.post("/inventory/opening-counts")
def opening_count(body: dict, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    it = db.get(Item, body.get("item_id"))
    if not it or not it.track_stock:
        err(422, "Select an item that is marked Track stock")
    q = qty(body.get("quantity"), "opening quantity", allow_zero=True)
    inv.post_movement(db, admin, it, "opening_count", q, parse_date(body.get("date") or today_ist()),
                      body.get("reason") or "Manually confirmed opening count", "manual")
    audit(db, admin, "opening_count", "item", it.id, after={"qty": q, "date": body.get("date")})
    db.commit()
    return inv.stock_view(db, it)


@router.post("/inventory/adjustments")
def adjustment(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    it = db.get(Item, body.get("item_id"))
    if not it or not it.track_stock:
        err(422, "Select an item that is marked Track stock")
    mtype = body.get("movement_type")
    if mtype not in ("adjustment_in", "adjustment_out", "wastage", "sale_return", "supplier_return", "other_in", "other_out"):
        err(422, "Invalid movement type")
    if not (body.get("reason") or "").strip():
        err(422, "A reason is required for every adjustment")
    inv.post_movement(db, user, it, mtype, qty(body.get("quantity")), parse_date(body.get("date") or today_ist()), body["reason"], "manual")
    audit(db, user, "adjustment", "item", it.id, after=body, reason=body["reason"])
    db.commit()
    return inv.stock_view(db, it)


# ------------------------------------------------------------------ purchases
def purchase_out(db, p: PurchaseBill):
    e = db.query(Expense).filter(Expense.purchase_bill_id == p.id).first()
    es = ledger.expense_summary(db, e) if e else {}
    return {"id": p.id, "vendor_id": p.vendor_id, "vendor": p.vendor.name, "invoice_no": p.invoice_no,
            "invoice_date": p.invoice_date.isoformat(), "due_date": p.due_date.isoformat() if p.due_date else None,
            "subtotal": p.subtotal, "discount": p.discount, "tax": p.tax, "total": p.total, "notes": p.notes,
            "expense_id": e.id if e else None, "paid": es.get("paid"), "due": es.get("due"), "payment_status": es.get("status"),
            "lines": [{"item_id": l.item_id, "description": l.description, "quantity": l.quantity, "unit": l.unit,
                       "conversion_factor": l.conversion_factor, "base_quantity": l.base_quantity,
                       "unit_price": l.unit_price, "line_total": l.line_total, "stock_posted": l.stock_posted} for l in p.lines]}


@router.get("/purchases")
def purchases(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [purchase_out(db, p) for p in db.query(PurchaseBill).order_by(PurchaseBill.invoice_date.desc(), PurchaseBill.id.desc()).limit(500)]


@router.get("/purchases/{pid}")
def purchase_detail(pid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    p = db.get(PurchaseBill, pid)
    if not p:
        err(404, "Purchase not found")
    return purchase_out(db, p)


@router.post("/purchases")
def add_purchase(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(Vendor, body.get("vendor_id"))
    if not v:
        err(422, "Select a supplier")
    lines_in = body.get("lines") or []
    if not lines_in:
        err(422, "Add at least one line")
    inv_date = parse_date(body.get("invoice_date") or today_ist())
    bill = PurchaseBill(vendor_id=v.id, invoice_no=body.get("invoice_no", ""), invoice_date=inv_date,
                        due_date=parse_date(body["due_date"]) if body.get("due_date") else None,
                        discount=money(body.get("discount", 0), "discount", allow_zero=True),
                        tax=money(body.get("tax", 0), "tax", allow_zero=True), total=ZERO,
                        notes=body.get("notes", ""), attachment=body.get("attachment", ""), created_by=user.id)
    db.add(bill)
    db.flush()
    sub, stock_posts = ZERO, []
    for i, ln in enumerate(lines_in, start=1):
        q = qty(ln.get("quantity"), f"line {i} quantity")
        price = money(ln.get("unit_price", 0), f"line {i} unit price", allow_zero=True)
        lt = money(ln["line_total"], f"line {i} total", allow_zero=True) if ln.get("line_total") not in (None, "") else (q * price).quantize(Decimal("0.01"))
        it = db.get(Item, ln["item_id"]) if ln.get("item_id") else None
        if ln.get("item_id") and not it:
            err(422, f"Line {i}: unknown item")
        unit = (ln.get("unit") or (it.base_unit if it else "")).strip()
        factor = qty(ln["conversion_factor"], f"line {i} conversion factor") if ln.get("conversion_factor") not in (None, "") else None
        base_q = None
        if it and it.track_stock:
            if factor is None:
                if unit.lower() == it.base_unit.lower():
                    factor = Decimal("1")
                else:
                    err(422, f"Line {i}: '{unit}' differs from base unit '{it.base_unit}' — enter the conversion factor yourself "
                             "(it is never inferred from the product name).")
            base_q = q * factor
        pl = PurchaseLine(bill_id=bill.id, item_id=it.id if it else None, description=ln.get("description") or (it.name if it else ""),
                          quantity=q, unit=unit, conversion_factor=factor, base_quantity=base_q, unit_price=price, line_total=lt)
        db.add(pl)
        sub += lt
        if it and it.track_stock and base_q:
            stock_posts.append((it, base_q, pl))
    bill.subtotal = sub
    bill.total = sub - bill.discount + bill.tax
    if bill.total <= 0:
        err(422, "Purchase total must be greater than zero")
    db.flush()
    for it, bq, pl in stock_posts:
        inv.post_movement(db, user, it, "purchase_in", bq, inv_date, f"Purchase {bill.invoice_no or bill.id}", "purchase", bill.id)
        pl.stock_posted = True
    e = Expense(expense_date=inv_date, category="Purchases", description=f"Supplier bill {bill.invoice_no}".strip(), vendor_id=v.id,
                payee_name=v.name, bill_ref=bill.invoice_no, total=bill.total, due_date=bill.due_date,
                attachment=bill.attachment, purchase_bill_id=bill.id, created_by=user.id)
    db.add(e)
    db.flush()
    audit(db, user, "create", "purchase", bill.id, after={"vendor": v.name, "total": bill.total})
    from .money import PaymentIn, _pay
    for p in body.get("payments") or []:
        _pay(db, user, e, PaymentIn(**p))
    db.commit()
    return purchase_out(db, bill)


# ------------------------------------------------------------------ imports
def _row_out(db, r: ImportRow):
    it = db.get(Item, r.item_id) if r.item_id else None
    sg = db.get(Item, r.suggested_item_id) if r.suggested_item_id else None
    status = "excluded" if not r.accepted else ("mapped" if it else ("new_item" if r.create_item else "unmapped"))
    if r.row_type not in ("item", "ditto"):
        status = "structural"
    return {"id": r.id, "seq": r.seq, "page": r.page, "row_type": r.row_type, "raw_name": r.raw_name, "name": r.name,
            "category": r.category, "department": r.department, "qty": r.qty, "amount": r.amount, "uom": r.uom,
            "cancel_orders": r.cancel_orders, "confidence": r.confidence, "notes": r.notes, "accepted": r.accepted,
            "exclude_reason": r.exclude_reason, "item_id": r.item_id, "item_name": it.name if it else None,
            "suggested_item_id": r.suggested_item_id, "suggested_item_name": sg.name if sg else None,
            "create_item": r.create_item, "needs_review": r.needs_review, "match_status": status}


def batch_summary(db, b: ImportBatch):
    rows = b.rows
    items = [r for r in rows if r.row_type in ("item", "ditto")]
    accepted = [r for r in items if r.accepted]
    unresolved = [r for r in accepted if b.report_type == "item_sales" and not r.item_id and not r.create_item]
    sq, sa = sum((r.qty or ZERO for r in accepted), ZERO), sum((r.amount or ZERO for r in accepted), ZERO)
    s = {"rows_total": len(rows), "item_rows": len(items), "accepted_rows": len(accepted),
         "excluded_structural": len([r for r in rows if r.row_type not in ("item", "ditto")]),
         "unresolved": len(unresolved), "needs_review": len([r for r in accepted if r.needs_review]),
         "accepted_qty": sq, "accepted_amount": sa,
         "printed_total": b.printed_grand_total, "printed_qty": b.printed_grand_qty}
    if b.printed_grand_total is not None:
        s["amount_variance"] = sa - b.printed_grand_total
    if b.printed_grand_qty is not None:
        s["qty_variance"] = sq - b.printed_grand_qty
    return s


def batch_out(db, b: ImportBatch, with_rows=True):
    d = {"id": b.id, "report_type": b.report_type, "filename": b.filename, "file_hash": b.file_hash,
         "report_date": b.report_date.isoformat() if b.report_date else None, "print_info": b.print_info,
         "outlet_name": b.outlet_name, "extraction_method": b.extraction_method, "status": b.status,
         "warnings": b.warnings or [], "duplicate_of_id": b.duplicate_of_id, "stored_file": b.stored_file,
         "uploaded_at": b.uploaded_at.isoformat(), "confirmed_at": b.confirmed_at.isoformat() if b.confirmed_at else None,
         "review_notes": b.review_notes, "summary": batch_summary(db, b)}
    if with_rows:
        d["rows"] = [_row_out(db, r) for r in b.rows]
    return d


def _match_row(db, r: ImportRow):
    r.item_id, r.suggested_item_id = None, None
    if r.row_type not in ("item", "ditto") or not r.name:
        return
    it = inv.find_item(db, r.name)
    if it:
        r.item_id = it.id
        return
    sg, score = inv.suggest_item(db, r.name)
    if sg:
        r.suggested_item_id = sg.id


def _find_duplicate(db, b: ImportBatch):
    q = db.query(ImportBatch).filter(ImportBatch.status == "confirmed", ImportBatch.report_type == b.report_type, ImportBatch.id != b.id)
    same = q.filter(ImportBatch.file_hash == b.file_hash).first()
    if same:
        return same, "This exact file was already imported."
    if b.report_type == "item_sales" and b.report_date:
        d = q.filter(ImportBatch.report_date == b.report_date).first()
        if d:
            return d, f"An Item Sales report for {b.report_date} was already imported (batch #{d.id})."
    return None, ""


@router.post("/imports/preview")
def preview(report_type: str = Form(...), report_date: str = Form(""), use_ai: bool = Form(False), file: UploadFile = File(...),
            db: Session = Depends(get_db), user: User = Depends(current_user)):
    if report_type not in ("item_sales", "stock_position"):
        err(422, "report_type must be item_sales or stock_position")
    fn = file.filename or "upload"
    ext = Path(fn).suffix.lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".csv"):
        err(422, "Supported files: PDF, PNG/JPG image, CSV")
    data = file.file.read()
    if not data:
        err(422, "Empty file")
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        err(413, "File too large")
    h = hashlib.sha256(data).hexdigest()
    # Re-uploading an unconfirmed draft of the same file reuses it (avoids a second slow OCR run)
    prior = db.query(ImportBatch).filter(ImportBatch.file_hash == h, ImportBatch.report_type == report_type,
                                         ImportBatch.status == "draft",
                                         ImportBatch.extraction_method == ("ai" if use_ai else ImportBatch.extraction_method)).first() if not use_ai else None
    if prior:
        return batch_out(db, prior)
    try:
        if use_ai:
            if report_type != "item_sales":
                err(422, "AI reading is only available for Item Sales (Stock Position needs names only; use OCR/CSV)")
            if ext == ".csv":
                err(422, "AI reading applies to PDFs/images, not CSV")
            from .. import ai
            if not ai.enabled():
                err(422, "AI reading is not enabled on this server (GEMINI_ENABLED / GEMINI_API_KEY)")
            res = ai.extract_item_sales(parsing.render_png_pages(data, fn))
        else:
            res = parsing.parse_item_sales(data, fn) if report_type == "item_sales" else parsing.parse_stock_position(data, fn)
    except RuntimeError as ex:
        err(422, str(ex))
    except ValueError as ex:
        err(422, f"Could not read the file: {ex}")
    stored = f"import_{h[:24]}{ext}"
    (get_settings().attachments_dir / stored).write_bytes(data)
    b = ImportBatch(report_type=report_type, filename=fn, file_hash=h, stored_file=stored, report_date=res.report_date,
                    print_info=res.print_info, outlet_name=res.outlet, extraction_method=res.method, status="draft",
                    printed_grand_total=res.printed_total, printed_grand_qty=res.printed_qty,
                    warnings=list(res.warnings), uploaded_by=user.id)
    if report_date:
        d = parse_date(report_date)
        if res.report_date and res.report_date != d:
            b.warnings.append(f"Entered date {d} differs from the date read from the report ({res.report_date}).")
        b.report_date = d
    db.add(b)
    db.flush()
    for r in res.rows:
        is_item = r.row_type in ("item", "ditto")
        row = ImportRow(batch_id=b.id, seq=r.seq, page=r.page, row_type=r.row_type, raw_name=r.raw_name, name=r.name,
                        category=r.category, department=r.department, qty=r.qty, amount=r.amount,
                        cancel_orders=r.cancel_orders, uom=r.uom, confidence=r.confidence, notes=r.notes,
                        needs_review=r.needs_review, exclude_reason=r.exclude_reason,
                        accepted=is_item and bool(r.name) and r.qty is not None and (r.amount is not None or report_type == "stock_position"))
        db.add(row)
        db.flush()
        if report_type == "item_sales":
            _match_row(db, row)
        else:
            row.item_id = (inv.find_item(db, row.name).id if inv.find_item(db, row.name) else None)
            row.qty = row.amount = None  # defensive: stock figures must never be stored
            row.accepted = bool(row.name)
    dup, msg = _find_duplicate(db, b)
    if dup:
        b.duplicate_of_id = dup.id
        b.warnings.append("DUPLICATE: " + msg)
    audit(db, user, "preview", "import_batch", b.id, after={"file": fn, "method": res.method, "type": report_type})
    db.commit()
    return batch_out(db, b)


@router.get("/imports")
def imports(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [batch_out(db, b, False) for b in db.query(ImportBatch).order_by(ImportBatch.id.desc()).limit(200)]


def _batch(db, bid) -> ImportBatch:
    b = db.get(ImportBatch, bid)
    if not b:
        err(404, "Import batch not found")
    return b


@router.get("/imports/{bid}")
def import_detail(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return batch_out(db, _batch(db, bid))


@router.patch("/imports/{bid}")
def edit_batch(bid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = _batch(db, bid)
    if b.status != "draft":
        err(409, "Only draft imports can be edited")
    if "report_date" in body:
        b.report_date = parse_date(body["report_date"])
        b.duplicate_of_id = None
        dup, msg = _find_duplicate(db, b)
        b.warnings = [w for w in (b.warnings or []) if not w.startswith("DUPLICATE")]
        if dup:
            b.duplicate_of_id = dup.id
            b.warnings = b.warnings + ["DUPLICATE: " + msg]
    if "review_notes" in body:
        b.review_notes = body["review_notes"]
    db.commit()
    return batch_out(db, b)


@router.patch("/imports/{bid}/rows/{rid}")
def edit_row(bid: int, rid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = _batch(db, bid)
    if b.status != "draft":
        err(409, "Only draft imports can be edited")
    r = db.get(ImportRow, rid)
    if not r or r.batch_id != bid:
        err(404, "Row not found")
    if "name" in body:
        r.name = body["name"].strip()
        if b.report_type == "item_sales":
            _match_row(db, r)
        r.needs_review = False
    if "qty" in body and b.report_type == "item_sales":
        r.qty = qty(body["qty"], "qty", allow_zero=True)
        r.needs_review = False
    if "amount" in body and b.report_type == "item_sales":
        r.amount = money(body["amount"], "amount", allow_zero=True)
        r.needs_review = False
    if "category" in body:
        r.category = body["category"]
    if "item_id" in body:
        if body["item_id"]:
            if not db.get(Item, body["item_id"]):
                err(422, "Unknown item")
            r.item_id, r.create_item = body["item_id"], False
        else:
            r.item_id = None
    if "create_item" in body:
        r.create_item = bool(body["create_item"])
        if r.create_item:
            r.item_id = None
    if "accepted" in body:
        r.accepted = bool(body["accepted"])
        if not r.accepted and not r.exclude_reason:
            r.exclude_reason = "Excluded by reviewer"
    if "needs_review" in body:
        r.needs_review = bool(body["needs_review"])
    db.commit()
    return _row_out(db, r) | {"summary": batch_summary(db, b)}


@router.post("/imports/{bid}/bulk")
def bulk(bid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Convenience for reviewers: apply a mapping decision to all still-unmapped rows.
    create_new => flag them to be created as PENDING catalogue items (still needs Confirm import)."""
    b = _batch(db, bid)
    if b.status != "draft":
        err(409, "Only draft imports can be edited")
    action = body.get("action")
    if action not in ("create_new", "use_suggestions"):
        err(422, "action must be create_new or use_suggestions")
    n = 0
    for r in b.rows:
        if r.row_type not in ("item", "ditto") or not r.accepted or r.item_id or not r.name:
            continue
        if action == "create_new" and not r.create_item:
            r.create_item, n = True, n + 1
        elif action == "use_suggestions" and r.suggested_item_id:
            r.item_id, r.create_item, n = r.suggested_item_id, False, n + 1
    audit(db, user, "bulk_" + action, "import_batch", b.id, after={"rows": n})
    db.commit()
    return {"updated": n, **batch_out(db, b)}


@router.post("/imports/{bid}/confirm")
def confirm(bid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = _batch(db, bid)
    if b.status != "draft":
        err(409, f"This import is already {b.status}")
    if not b.report_date and b.report_type == "item_sales":
        err(422, "Set the report date before confirming")
    dup, msg = _find_duplicate(db, b)
    override = bool(body.get("override_duplicate"))
    if dup:
        if not override:
            err(409, f"DUPLICATE IMPORT BLOCKED: {msg} Cancel it, or an admin may override with a reason.")
        if user.role != "admin":
            err(403, "Only an admin can override a duplicate import")
        if not (body.get("override_reason") or "").strip():
            err(422, "A reason is required to override a duplicate import")
    s = batch_summary(db, b)
    if s["unresolved"]:
        err(422, f"{s['unresolved']} accepted row(s) have no item mapping. Map each to an item, create a new item, or exclude it.")
    if s["accepted_rows"] == 0:
        err(422, "No accepted rows to import")
    warn = s["needs_review"] or (s.get("amount_variance") not in (None, ZERO)) or (s.get("qty_variance") not in (None, ZERO))
    if warn and not body.get("acknowledge_warnings"):
        err(422, "This batch has rows flagged for review or does not reconcile with the printed totals. "
                 "Review them and confirm with 'acknowledge warnings'.")
    created, linked = 0, 0
    if b.report_type == "stock_position":
        for r in b.rows:
            if not r.accepted or r.row_type != "item":
                continue
            if inv.find_item(db, r.name):
                continue
            inv.create_item(db, user, r.name, source_report="stock_position", source_name=r.raw_name,
                            uom_hint=r.uom, pending=True)  # track_stock stays False; NO quantities/values imported
            created += 1
        b.review_notes = (b.review_notes + f"\nCatalogue names only: {created} new pending items. Stock figures ignored.").strip()
    else:
        for r in b.rows:
            if not r.accepted or r.row_type not in ("item", "ditto"):
                continue
            it = db.get(Item, r.item_id) if r.item_id else None
            if not it:
                it = inv.find_item(db, r.name)
            if not it and r.create_item:
                it = inv.create_item(db, user, r.name, source_report="item_sales", source_name=r.raw_name,
                                     category=r.category, department=r.department, pending=True)
                created += 1
            if not it:
                err(422, f"Row '{r.name}' is unmapped")
            if r.raw_name and norm_name(r.raw_name) != it.norm_name:
                try:
                    inv.add_alias(db, user, it, r.raw_name, "item_sales")
                except Exception:
                    pass
            db.add(ItemSaleLine(batch_id=b.id, business_date=b.report_date, item_id=it.id, source_name=r.raw_name,
                                category=r.category, department=r.department, qty=r.qty, amount=r.amount))
            inv.post_sale_out(db, user, it, r.qty, b.report_date, b.id)
            linked += 1
    b.status, b.confirmed_by, b.confirmed_at = "confirmed", user.id, utcnow()
    b.override_duplicate = bool(dup and override)
    audit(db, user, "confirm", "import_batch", b.id,
          after={"summary": s, "created_items": created, "override": b.override_duplicate},
          reason=body.get("override_reason", ""))
    db.commit()
    return batch_out(db, b)


@router.post("/imports/{bid}/reject")
def reject(bid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = _batch(db, bid)
    if b.status != "draft":
        err(409, "Only drafts can be rejected")
    b.status = "rejected"
    b.review_notes = body.get("reason", "")
    audit(db, user, "reject", "import_batch", b.id, reason=body.get("reason", ""))
    db.commit()
    return batch_out(db, b, False)


@router.post("/imports/{bid}/reverse")
def reverse(bid: int, body: dict, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    b = _batch(db, bid)
    if b.status != "confirmed":
        err(409, "Only confirmed imports can be reversed")
    reason = (body.get("reason") or "").strip()
    if not reason:
        err(422, "A reason is required")
    for l in db.query(ItemSaleLine).filter(ItemSaleLine.batch_id == b.id):
        l.active = False
    for m in db.query(InventoryMovement).filter(InventoryMovement.import_batch_id == b.id, InventoryMovement.movement_type == "sale_out").all():
        db.add(InventoryMovement(item_id=m.item_id, business_date=today_ist(), movement_type="sale_return", quantity=-m.quantity,
                                 source_type="import_reversal", source_id=b.id, import_batch_id=None,
                                 reason=f"Reversal of import #{b.id}: {reason}", user_id=admin.id))
    b.status = "reversed"
    audit(db, admin, "reverse", "import_batch", b.id, reason=reason)
    db.commit()
    return batch_out(db, b, False)


@router.get("/imports/{bid}/file")
def import_file(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    from fastapi.responses import FileResponse
    b = _batch(db, bid)
    p = get_settings().attachments_dir / b.stored_file
    if not b.stored_file or not p.is_file():
        err(404, "Original file missing")
    return FileResponse(p, filename=b.filename)
