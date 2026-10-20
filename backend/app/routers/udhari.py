from typing import Any, Optional

from decimal import Decimal

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import ledger
from ..core import (
    admin_user, audit, current_user, err, get_setting, money, parse_date, today_ist, METHODS,
)
from ..db import get_db
from ..models import BillAdjustment, Customer, Receipt, ReceiptAllocation, SaleBill, User

router = APIRouter()
ZERO_D = Decimal("0")


class CustomerIn(BaseModel):
    name: str
    phone: str = ""
    address: str = ""
    notes: str = ""
    allow_duplicate: bool = False


class Alloc(BaseModel):
    bill_id: int
    amount: Any


class BillIn(BaseModel):
    customer_id: int
    bill_no: str
    pos_bill_no: str = ""
    business_date: Optional[str] = None
    total: Any
    paid_now: Any = 0
    method: Optional[str] = "cash"
    account_id: Optional[int] = None
    in_pos_report: bool = True
    count_as_new_sale: bool = False
    notes: str = ""
    attachment: str = ""
    lines: list[dict] = []
    allow_duplicate: bool = False
    post_paid_now_to_cashbook: Optional[bool] = None


class ReceiptIn(BaseModel):
    customer_id: int
    amount: Any
    receipt_date: Optional[str] = None
    method: str
    account_id: int
    reference: str = ""
    received_by: str = ""
    notes: str = ""
    allocations: list[Alloc] = []
    auto_allocate: bool = False


def cust_out(db, c: Customer, with_balance=True):
    d = {"id": c.id, "name": c.name, "phone": c.phone, "address": c.address, "notes": c.notes, "active": c.active,
         "created_at": c.created_at.isoformat()}
    if with_balance:
        d.update(ledger.customer_balance(db, c.id))
    return d


@router.get("/customers")
def customers(q: str = "", filter: str = "", db: Session = Depends(get_db), _: User = Depends(current_user)):
    qs = db.query(Customer)
    if q:
        like = f"%{q.strip()}%"
        qs = qs.filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like)))
    all_custs = qs.order_by(Customer.name).all()
    cust_ids = [c.id for c in all_custs]
    balances = ledger.batch_customer_balances(db, cust_ids)

    out = []
    for c in all_custs:
        d = {"id": c.id, "name": c.name, "phone": c.phone, "address": c.address, "notes": c.notes, "active": c.active,
             "created_at": c.created_at.isoformat()}
        d.update(balances.get(c.id, {
            "outstanding": ZERO_D, "advance": ZERO_D, "net": ZERO_D,
            "oldest_open_bill_date": None, "last_collection": None, "open_bills": 0
        }))
        out.append(d)

    od = int(get_setting(db, "overdue_days") or 30)
    if filter == "owing":
        out = [c for c in out if c["outstanding"] > 0]
    elif filter == "overdue":
        out = [c for c in out if c["oldest_open_bill_date"] and (today_ist() - parse_date(c["oldest_open_bill_date"])).days > od]
    return out


@router.post("/customers")
def add_customer(body: CustomerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    name = body.name.strip()
    if not name:
        err(422, "Customer name is required")
    if get_setting(db, "phone_mandatory") == "true" and not body.phone.strip():
        err(422, "Phone is mandatory (see Settings)")
    if not body.allow_duplicate:
        dup = db.query(Customer).filter(
            or_(Customer.name.ilike(name), (Customer.phone == body.phone.strip()) if body.phone.strip() else False)).first()
        if dup:
            err(409, f"A similar customer already exists: {dup.name} ({dup.phone or 'no phone'}), id {dup.id}. "
                     "Select it, or confirm to create a separate customer.")
    c = Customer(name=name, phone=body.phone.strip(), address=body.address, notes=body.notes)
    db.add(c)
    db.flush()
    audit(db, user, "create", "customer", c.id, after={"name": name, "phone": c.phone})
    db.commit()
    return cust_out(db, c)


@router.patch("/customers/{cid}")
def edit_customer(cid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = db.get(Customer, cid)
    if not c:
        err(404, "Customer not found")
    before = {k: getattr(c, k) for k in ("name", "phone", "address", "notes", "active")}
    for k in ("name", "phone", "address", "notes", "active"):
        if k in body:
            setattr(c, k, body[k])
    if not c.name.strip():
        db.rollback()
        err(422, "Name is required")
    audit(db, user, "update", "customer", c.id, before=before, after=body)
    db.commit()
    return cust_out(db, c)


def _get_customer(db, cid) -> Customer:
    c = db.get(Customer, cid)
    if not c:
        err(404, "Customer not found")
    return c


@router.get("/customers/{cid}")
def customer_detail(cid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    c = _get_customer(db, cid)
    rcs = db.query(Receipt).filter(Receipt.customer_id == cid).order_by(Receipt.receipt_date.desc(), Receipt.id.desc()).all()
    return {**cust_out(db, c), "bills": ledger.customer_bills(db, cid), "receipts": [receipt_out(db, r) for r in rcs]}


def receipt_out(db, r: Receipt):
    allocs = db.query(ReceiptAllocation).filter(ReceiptAllocation.receipt_id == r.id).all()
    return {"id": r.id, "receipt_no": r.receipt_no, "customer_id": r.customer_id, "customer": r.customer.name,
            "receipt_date": r.receipt_date.isoformat(), "amount": r.amount, "method": r.method,
            "account_id": r.account_id, "account": r.account.name, "reference": r.reference,
            "received_by": r.received_by, "notes": r.notes, "status": r.status, "kind": r.kind,
            "post_to_cashbook": r.post_to_cashbook, "void_reason": r.void_reason,
            "unallocated": ledger.receipt_unallocated(db, r),
            "allocations": [{"bill_id": a.bill_id, "bill_no": a.bill.bill_no, "amount": a.amount, "active": a.active}
                            for a in allocs]}


@router.get("/customers/{cid}/ledger")
def customer_ledger(cid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """Chronological statement: bills = debit, receipts = credit, with running balance."""
    from ..reports import statement_rows
    c = _get_customer(db, cid)
    rows, closing = statement_rows(db, c)
    return {"customer": cust_out(db, c, False), "rows": rows, "closing_balance": closing}


# ---- bills
@router.get("/credit-bills")
def bills(customer_id: Optional[int] = None, open_only: bool = False, db: Session = Depends(get_db), _: User = Depends(current_user)):
    if customer_id:
        return ledger.customer_bills(db, customer_id, open_only)
    out = []
    for b in db.query(SaleBill).order_by(SaleBill.business_date.desc(), SaleBill.id.desc()).limit(500):
        s = ledger.bill_summary(db, b)
        s["customer"] = b.customer.name
        out.append(s)
    return [s for s in out if s["outstanding"] > 0] if open_only else out


@router.post("/credit-bills")
def add_bill(body: BillIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get_customer(db, body.customer_id)
    total = money(body.total, "bill total")
    paid = money(body.paid_now or 0, "amount received now", allow_zero=True)
    if paid > 0 and not body.account_id:
        err(422, "Select the account that received the amount paid now")
    bill = ledger.create_bill(
        db, user, customer=c, bill_no=body.bill_no, pos_bill_no=body.pos_bill_no,
        business_date=parse_date(body.business_date) if body.business_date else today_ist(),
        total=total, paid_now=paid, method=body.method, account_id=body.account_id,
        in_pos_report=body.in_pos_report, count_as_new_sale=body.count_as_new_sale, notes=body.notes,
        attachment=body.attachment, lines=body.lines, force_duplicate=body.allow_duplicate,
        post_paid_now=body.post_paid_now_to_cashbook)
    db.commit()
    return ledger.bill_summary(db, bill)


@router.get("/credit-bills/{bid}")
def bill_detail(bid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    b = db.get(SaleBill, bid)
    if not b:
        err(404, "Bill not found")
    allocs = db.query(ReceiptAllocation).filter(ReceiptAllocation.bill_id == bid).all()
    return {**ledger.bill_summary(db, b), "customer": b.customer.name,
            "lines": [{"item_name": l.item_name, "quantity": l.quantity, "unit": l.unit, "unit_price": l.unit_price,
                       "line_total": l.line_total} for l in b.lines],
            "allocations": [{"receipt_id": a.receipt_id, "receipt_no": a.receipt.receipt_no, "amount": a.amount,
                             "active": a.active and a.receipt.status == "posted", "date": a.receipt.receipt_date.isoformat()}
                            for a in allocs]}


@router.post("/credit-bills/{bid}/void")
def void_bill(bid: int, body: dict, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    b = db.get(SaleBill, bid)
    if not b:
        err(404, "Bill not found")
    ledger.void_bill(db, admin, b, body.get("reason", ""))
    db.commit()
    return ledger.bill_summary(db, b)


@router.post("/credit-bills/{bid}/adjustments")
def adjust_bill(bid: int, body: dict, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    """Credit note / write-off (admin only, reason required)."""
    b = db.get(SaleBill, bid)
    if not b:
        err(404, "Bill not found")
    kind = body.get("kind")
    if kind not in ("credit_note", "writeoff"):
        err(422, "kind must be credit_note or writeoff")
    amt = money(body.get("amount"), "amount")
    out = ledger.bill_summary(db, b)["outstanding"]
    if amt > out:
        err(422, f"Amount exceeds the open balance ₹{out}")
    if not (body.get("reason") or "").strip():
        err(422, "A reason is required")
    a = BillAdjustment(bill_id=b.id, kind=kind, amount=amt, reason=body["reason"], adj_date=today_ist(), created_by=admin.id)
    db.add(a)
    db.flush()
    audit(db, admin, "create", "bill_adjustment", a.id, after={"bill": b.id, "kind": kind, "amount": amt}, reason=body["reason"])
    db.commit()
    return ledger.bill_summary(db, b)


# ---- receipts
@router.get("/receipts")
def receipts(customer_id: Optional[int] = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    q = db.query(Receipt).order_by(Receipt.receipt_date.desc(), Receipt.id.desc())
    if customer_id:
        q = q.filter(Receipt.customer_id == customer_id)
    return [receipt_out(db, r) for r in q.limit(500)]


@router.get("/receipts/suggest-allocation")
def suggest(customer_id: int, amount: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return ledger.suggest_allocation(db, customer_id, money(amount))


@router.post("/receipts")
def add_receipt(body: ReceiptIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    c = _get_customer(db, body.customer_id)
    amt = money(body.amount, "receipt amount")
    rc = ledger.create_receipt(
        db, user, customer=c, amount=amt, receipt_date=parse_date(body.receipt_date) if body.receipt_date else today_ist(),
        method=body.method, account_id=body.account_id, reference=body.reference, received_by=body.received_by,
        notes=body.notes, allocations=[a.model_dump() for a in body.allocations], auto_allocate=body.auto_allocate)
    db.commit()
    return receipt_out(db, rc)


@router.get("/receipts/{rid}")
def receipt_detail(rid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    r = db.get(Receipt, rid)
    if not r:
        err(404, "Receipt not found")
    return receipt_out(db, r)


@router.post("/receipts/{rid}/allocations")
def allocate_more(rid: int, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Apply an existing customer advance (unallocated amount) to open bills."""
    r = db.get(Receipt, rid)
    if not r or r.status != "posted":
        err(404, "Receipt not found or voided")
    ledger.apply_allocations(db, r, r.customer, body.get("allocations", []), r.amount)
    audit(db, user, "allocate", "receipt", r.id, after=body)
    db.commit()
    return receipt_out(db, r)


@router.post("/receipts/{rid}/void")
def void_receipt(rid: int, body: dict, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    r = db.get(Receipt, rid)
    if not r:
        err(404, "Receipt not found")
    ledger.void_receipt(db, admin, r, body.get("reason", ""))
    db.commit()
    return receipt_out(db, r)


@router.post("/credit-bills/import-csv")
def import_old_udhari(dry_run: bool = True, file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Onboarding: load existing unpaid bills from CSV (columns: customer, phone, bill_no, date, amount[, paid][, notes]).
    Dry run validates and reports per-row problems; a real run is all-or-nothing. Bills are marked 'already in POS report'
    and nothing is posted to the cashbook (money was received/ will be received through normal receipts)."""
    import csv, io
    raw = file.file.read().decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        err(422, "The CSV has no rows")
    norm = lambda r: {(k or "").strip().lower(): (v or "").strip() for k, v in r.items()}
    report, seen = [], set()
    plan = []
    for i, r in enumerate(map(norm, rows), start=2):
        issues = []
        name, phone, no = r.get("customer") or r.get("name") or "", r.get("phone", ""), r.get("bill_no", "")
        try:
            d = parse_date(r.get("date") or "")
        except Exception:
            d = None
            issues.append("date must be YYYY-MM-DD")
        try:
            total = money(r.get("amount"), "amount")
            paid = money(r.get("paid") or 0, "paid", allow_zero=True)
            if paid >= total:
                issues.append("paid must be less than amount (fully paid bills are not udhari)")
        except Exception as ex:  # HTTPException from money()
            total = paid = None
            issues.append(getattr(ex, "detail", str(ex)))
        if not name:
            issues.append("customer is required")
        if not no:
            issues.append("bill_no is required")
        elif no in seen or db.query(SaleBill).filter(SaleBill.bill_no == no, SaleBill.status == "posted").first():
            issues.append("duplicate bill_no")
        seen.add(no)
        report.append({"line": i, "customer": name, "bill_no": no, "amount": str(total) if total is not None else r.get("amount"), "issues": issues})
        plan.append((name, phone, no, d, total, paid, r.get("notes", ""), r.get("pos_bill_no", "")))
    bad = [x for x in report if x["issues"]]
    if dry_run or bad:
        return {"ok": not bad, "committed": False, "rows": report, "message": "Fix the listed rows and upload again." if bad else "Looks valid. Upload again with dry_run=false to import."}
    created = 0
    for name, phone, no, d, total, paid, notes, pos in plan:
        c = db.query(Customer).filter(Customer.name.ilike(name), Customer.phone == phone).first()
        if not c:
            c = Customer(name=name, phone=phone)
            db.add(c)
            db.flush()
        b = SaleBill(bill_no=no, pos_bill_no=pos, customer_id=c.id, business_date=d, total=total, paid_now=ZERO_D, in_pos_report=True,
                     notes=notes or "Imported opening udhari", created_by=user.id)
        db.add(b)
        db.flush()
        if paid > 0:  # earlier part-payment: allocation only, no cash movement (already happened before go-live)
            from ..models import Receipt as R
            rc = R(receipt_no=ledger.next_number(db, "receipt_prefix", R, R.receipt_no, "RC"), customer_id=c.id, receipt_date=d, amount=paid,
                   method="other", account_id=db.query(__import__("app.models", fromlist=["Account"]).Account).filter_by(is_physical_cash=False).first().id,
                   kind="bill_time", post_to_cashbook=False, notes="Opening balance import: received before go-live", created_by=user.id)
            db.add(rc)
            db.flush()
            db.add(ReceiptAllocation(receipt_id=rc.id, bill_id=b.id, amount=paid))
        created += 1
    audit(db, user, "import_opening_udhari", "sale_bill", "bulk", after={"bills": created, "file": file.filename})
    db.commit()
    return {"ok": True, "committed": True, "rows": report, "message": f"Imported {created} bill(s)."}
