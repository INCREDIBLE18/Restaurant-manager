"""Report builders. Each returns {title, columns, rows, totals?} so screen and CSV share identical numbers."""
import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from . import ledger
from .core import err, get_setting, parse_date, today_ist
from .models import (
    Account, BillAdjustment, CashMovement, Customer, DayClose, Expense, ExpensePayment, ImportBatch, InventoryMovement,
    Item, ItemSaleLine, OwnerLedgerEntry, PurchaseBill, Receipt, ReceiptAllocation, SaleBill,
)

ZERO = Decimal("0")


def _rng(date_from, date_to):
    return (parse_date(date_from) if date_from else None), (parse_date(date_to) if date_to else None)


def _in(d, a, b):
    return (a is None or d >= a) and (b is None or d <= b)


def statement_rows(db: Session, c: Customer, date_from=None, date_to=None):
    events = []
    for b in db.query(SaleBill).filter(SaleBill.customer_id == c.id).all():
        if b.status == "posted":
            events.append((b.business_date, 0, b.id, "Bill", b.bill_no, b.total, ZERO, "", b.status))
    for r in db.query(Receipt).filter(Receipt.customer_id == c.id).all():
        if r.status == "posted":
            allocs = db.query(ReceiptAllocation).filter(ReceiptAllocation.receipt_id == r.id, ReceiptAllocation.active.is_(True)).all()
            txt = ", ".join(f"{a.bill.bill_no}: ₹{a.amount}" for a in allocs)
            un = ledger.receipt_unallocated(db, r)
            if un > 0:
                txt += (", " if txt else "") + f"Unallocated advance: ₹{un}"
            events.append((r.receipt_date, 1, r.id, f"Receipt ({r.method})", r.receipt_no, ZERO, r.amount, txt, r.status))
    for a in db.query(BillAdjustment).join(SaleBill).filter(SaleBill.customer_id == c.id, BillAdjustment.active.is_(True)).all():
        events.append((a.adj_date, 2, a.id, a.kind.replace("_", " ").title(), f"#{a.bill_id}", ZERO, a.amount, a.reason, "posted"))
    events.sort(key=lambda e: (e[0], e[1], e[2]))
    bal, rows = ZERO, []
    a, b = date_from, date_to
    opening = ZERO
    for e in events:
        if a and e[0] < a:
            opening += e[5] - e[6]
    bal = opening
    if a:
        rows.append({"date": a.isoformat(), "type": "Opening balance", "ref": "", "debit": ZERO, "credit": ZERO,
                     "details": "", "balance": opening})
    for e in events:
        if not _in(e[0], a, b):
            continue
        bal += e[5] - e[6]
        rows.append({"date": e[0].isoformat(), "type": e[3], "ref": e[4], "debit": e[5], "credit": e[6],
                     "details": e[7], "balance": bal})
    return rows, bal


def _tbl(title, columns, rows, totals=None):
    return {"title": title, "columns": columns, "rows": rows, "totals": totals or {}}


def customer_outstanding(db, p):
    out = []
    od = get_setting(db, "overdue_days")
    for c in db.query(Customer).order_by(Customer.name):
        bal = ledger.customer_balance(db, c.id)
        if bal["outstanding"] <= 0 and bal["advance"] <= 0:
            continue
        oldest = bal["oldest_open_bill_date"]
        out.append({"customer": c.name, "phone": c.phone, "total_due": bal["outstanding"], "advance_credit": bal["advance"],
                    "open_bills": bal["open_bills"], "oldest_open_bill": oldest or "",
                    "days_overdue": (today_ist() - date.fromisoformat(oldest)).days if oldest else 0,
                    "last_collection": bal["last_collection"] or ""})
    return _tbl("Customer Outstanding", ["customer", "phone", "total_due", "advance_credit", "open_bills", "oldest_open_bill", "days_overdue", "last_collection"],
                out, {"total_due": sum((r["total_due"] for r in out), ZERO)})


def customer_statement(db, p):
    cid = p.get("customer_id")
    c = db.get(Customer, int(cid)) if cid else None
    if not c:
        err(422, "customer_id is required")
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    rows, closing = statement_rows(db, c, a, b)
    return _tbl(f"Statement — {c.name}", ["date", "type", "ref", "debit", "credit", "details", "balance"], rows, {"closing_balance": closing})


def udhari_collections(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    rows = []
    for r in db.query(Receipt).order_by(Receipt.receipt_date, Receipt.id):
        if r.status != "posted" or not _in(r.receipt_date, a, b):
            continue
        al = db.query(ReceiptAllocation).filter(ReceiptAllocation.receipt_id == r.id, ReceiptAllocation.active.is_(True)).all()
        rows.append({"date": r.receipt_date.isoformat(), "receipt_no": r.receipt_no, "customer": r.customer.name, "amount": r.amount,
                     "method": r.method, "account": r.account.name, "received_by": r.received_by, "kind": r.kind,
                     "allocations": ", ".join(f"{x.bill.bill_no}: {x.amount}" for x in al), "reference": r.reference})
    return _tbl("Udhari Collections", ["date", "receipt_no", "customer", "amount", "method", "account", "received_by", "kind", "allocations", "reference"],
                rows, {"amount": sum((r["amount"] for r in rows), ZERO)})


def bill_outstanding(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    rows = []
    for bl in db.query(SaleBill).order_by(SaleBill.business_date, SaleBill.id):
        if bl.status != "posted" or not _in(bl.business_date, a, b):
            continue
        s = ledger.bill_summary(db, bl)
        if p.get("open_only", "true") != "false" and s["outstanding"] <= 0:
            continue
        rows.append({"bill_no": bl.bill_no, "pos_bill_no": bl.pos_bill_no, "customer": bl.customer.name, "date": s["business_date"],
                     "total": s["total"], "collected": s["collected"], "adjusted": s["adjusted"], "outstanding": s["outstanding"],
                     "age_days": s["age_days"], "in_pos_report": "yes" if bl.in_pos_report else "no"})
    return _tbl("Bill Outstanding Detail", ["bill_no", "pos_bill_no", "customer", "date", "total", "collected", "adjusted", "outstanding", "age_days", "in_pos_report"],
                rows, {"total": sum((r["total"] for r in rows), ZERO), "outstanding": sum((r["outstanding"] for r in rows), ZERO)})


def _expenses(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    return [e for e in db.query(Expense).order_by(Expense.expense_date, Expense.id) if e.status == "posted" and _in(e.expense_date, a, b)]


def expense_summary(db, p):
    agg = defaultdict(lambda: [ZERO, ZERO, ZERO])
    for e in _expenses(db, p):
        s = ledger.expense_summary(db, e)
        agg[e.category][0] += s["total"]
        agg[e.category][1] += s["paid"]
        agg[e.category][2] += s["due"]
    rows = [{"category": k, "incurred": v[0], "paid": v[1], "unpaid": v[2]} for k, v in sorted(agg.items())]
    return _tbl("Expense Summary", ["category", "incurred", "paid", "unpaid"], rows,
                {k: sum((r[k] for r in rows), ZERO) for k in ("incurred", "paid", "unpaid")})


def unpaid_expenses(db, p):
    rows = []
    for e in _expenses(db, p):
        s = ledger.expense_summary(db, e)
        if s["due"] > 0:
            rows.append({"date": s["expense_date"], "payee": s["payee_name"], "category": e.category, "bill_ref": e.bill_ref, "due_date": s["due_date"] or "",
                         "total": s["total"], "paid": s["paid"], "due": s["due"], "status": s["status"], "last_payment": s["last_payment_date"] or "",
                         "sources": ", ".join(s["sources"])})
    return _tbl("Unpaid / Part-paid Expenses", ["date", "payee", "category", "bill_ref", "due_date", "total", "paid", "due", "status", "last_payment", "sources"],
                rows, {"due": sum((r["due"] for r in rows), ZERO)})


def paid_by_source(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    agg = defaultdict(lambda: ZERO)
    for pay in db.query(ExpensePayment).filter(ExpensePayment.status == "posted"):
        if not _in(pay.paid_date, a, b):
            continue
        src = pay.account.name if pay.account else "Owner (personal funds)"
        agg[(src, pay.paid_by or "—", pay.method)] += pay.amount
    rows = [{"source": k[0], "paid_by": k[1], "method": k[2], "amount": v} for k, v in sorted(agg.items())]
    return _tbl("Paid By / Source", ["source", "paid_by", "method", "amount"], rows, {"amount": sum((r["amount"] for r in rows), ZERO)})


def owner_ledger_report(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    rows, bal = [], ZERO
    for r in db.query(OwnerLedgerEntry).filter(OwnerLedgerEntry.active.is_(True)).order_by(OwnerLedgerEntry.entry_date, OwnerLedgerEntry.id):
        if r.kind == "funded":
            bal += r.amount
        elif r.kind == "reimbursement":
            bal -= r.amount
        if _in(r.entry_date, a, b):
            rows.append({"date": r.entry_date.isoformat(), "kind": r.kind, "amount": r.amount, "note": r.note, "due_to_owner_after": bal})
    return _tbl("Owner Reimbursement Ledger", ["date", "kind", "amount", "note", "due_to_owner_after"], rows, {"due_to_owner": ledger.owner_balance(db)["due_to_owner"]})


def cashbook(db, p):
    aid = p.get("account_id")
    acc = db.get(Account, int(aid)) if aid else None
    if not acc:
        err(422, "account_id is required")
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    mvs = db.query(CashMovement).filter(CashMovement.account_id == acc.id).order_by(CashMovement.business_date, CashMovement.id).all()
    bal = acc.opening_balance + sum((m.amount for m in mvs if a and m.business_date < a), ZERO)
    rows = [{"date": (a or acc.opening_date or today_ist()).isoformat(), "type": "opening_balance", "reference": "", "note": "", "in": ZERO, "out": ZERO, "balance": bal}]
    for m in mvs:
        if not _in(m.business_date, a, b):
            continue
        bal += m.amount
        rows.append({"date": m.business_date.isoformat(), "type": m.movement_type, "reference": f"{m.source_type}#{m.source_id or ''}",
                     "note": m.note, "in": m.amount if m.amount > 0 else ZERO, "out": -m.amount if m.amount < 0 else ZERO, "balance": bal})
    return _tbl(f"Cashbook — {acc.name}", ["date", "type", "reference", "note", "in", "out", "balance"], rows,
                {"closing_balance": bal, "in": sum((r["in"] for r in rows), ZERO), "out": sum((r["out"] for r in rows), ZERO)})


def daily_closing(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    rows = []
    for d in db.query(DayClose).order_by(DayClose.business_date):
        if not _in(d.business_date, a, b):
            continue
        rows.append({"date": d.business_date.isoformat(), "status": d.status, "opening_cash": d.opening_cash, "pos_total_sales": d.pos_total_sales,
                     "cash_sales": d.cash_sales, "upi_sales": d.upi_sales, "card_sales": d.card_sales, "credit_sales": d.credit_sales,
                     "expected_cash": d.expected_cash, "physical_counted": d.physical_counted, "variance": d.variance,
                     "reason": d.variance_reason})
    return _tbl("Daily Closing", ["date", "status", "opening_cash", "pos_total_sales", "cash_sales", "upi_sales", "card_sales", "credit_sales",
                                  "expected_cash", "physical_counted", "variance", "reason"], rows,
                {"variance": sum((r["variance"] or ZERO for r in rows), ZERO)})


def item_sales_summary(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    agg = defaultdict(lambda: [ZERO, ZERO])
    for l in db.query(ItemSaleLine).filter(ItemSaleLine.active.is_(True)):
        if not _in(l.business_date, a, b) or (p.get("category") and l.category != p["category"]):
            continue
        k = (l.item.name, l.category, l.department)
        agg[k][0] += l.qty
        agg[k][1] += l.amount
    rows = [{"item": k[0], "category": k[1], "department": k[2], "qty_sold": v[0], "amount": v[1]} for k, v in sorted(agg.items())]
    return _tbl("Item Sales Summary (report data — not cash collected)", ["item", "category", "department", "qty_sold", "amount"], rows,
                {"qty_sold": sum((r["qty_sold"] for r in rows), ZERO), "amount": sum((r["amount"] for r in rows), ZERO)})


def purchase_summary(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    rows = []
    for pb in db.query(PurchaseBill).order_by(PurchaseBill.invoice_date, PurchaseBill.id):
        if not _in(pb.invoice_date, a, b):
            continue
        e = db.query(Expense).filter(Expense.purchase_bill_id == pb.id).first()
        s = ledger.expense_summary(db, e) if e else {}
        rows.append({"date": pb.invoice_date.isoformat(), "supplier": pb.vendor.name, "invoice_no": pb.invoice_no, "lines": len(pb.lines),
                     "total": pb.total, "paid": s.get("paid", ZERO), "due": s.get("due", ZERO), "status": s.get("status", "")})
    return _tbl("Purchase Summary", ["date", "supplier", "invoice_no", "lines", "total", "paid", "due", "status"], rows,
                {"total": sum((r["total"] for r in rows), ZERO), "due": sum((r["due"] for r in rows), ZERO)})


def stock_movements(db, p):
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    q = db.query(InventoryMovement).order_by(InventoryMovement.item_id, InventoryMovement.business_date, InventoryMovement.id)
    if p.get("item_id"):
        q = q.filter(InventoryMovement.item_id == int(p["item_id"]))
    rows, run, cur, base = [], ZERO, None, False
    for m in q:
        if m.item_id != cur:
            cur, run, base = m.item_id, ZERO, False
        if m.movement_type == "opening_count":
            run, base = m.quantity, True
        else:
            run += m.quantity
        if _in(m.business_date, a, b):
            rows.append({"item": m.item.name, "date": m.business_date.isoformat(), "type": m.movement_type, "quantity": m.quantity,
                         "running": run, "baseline": "set" if base else "Opening baseline unknown", "source": f"{m.source_type}#{m.source_id or ''}", "reason": m.reason})
    return _tbl("Stock Movement Ledger", ["item", "date", "type", "quantity", "running", "baseline", "source", "reason"], rows)


def import_history(db, p):
    rows = []
    for bt in db.query(ImportBatch).order_by(ImportBatch.id.desc()):
        rows.append({"batch": bt.id, "type": bt.report_type, "report_date": bt.report_date.isoformat() if bt.report_date else "",
                     "uploaded": bt.uploaded_at.isoformat(timespec="minutes"), "file": bt.filename, "method": bt.extraction_method,
                     "rows": len(bt.rows), "warnings": len(bt.warnings or []), "status": bt.status})
    return _tbl("Import History", ["batch", "type", "report_date", "uploaded", "file", "method", "rows", "warnings", "status"], rows)


def customer_aging(db, p):
    """Open udhari split by bill age, per customer."""
    from .routers.insights import BUCKETS
    today = today_ist()
    rows = {}
    for b in db.query(SaleBill).filter(SaleBill.status == "posted").order_by(SaleBill.business_date):
        out = ledger.bill_summary(db, b)["outstanding"]
        if out <= 0:
            continue
        r = rows.setdefault(b.customer_id, {"customer": b.customer.name, "phone": b.customer.phone,
                                            **{k: ZERO for k, _, _ in BUCKETS}, "total": ZERO})
        age = (today - b.business_date).days
        for k, lo, hi in BUCKETS:
            if lo <= age <= hi:
                r[k] += out
                break
        r["total"] += out
    out_rows = sorted(rows.values(), key=lambda r: r["total"], reverse=True)
    cols = ["customer", "phone"] + [k for k, _, _ in BUCKETS] + ["total"]
    return _tbl("Customer Aging (by bill age, days)", cols, out_rows,
                {k: sum((r[k] for r in out_rows), ZERO) for k in [k for k, _, _ in BUCKETS] + ["total"]})


def pnl_summary(db, p):
    """Operational profit estimate: POS sales (typed at day close, else Item Sales report) minus expenses incurred.
    Not a statutory/GST P&L: no inventory valuation or depreciation."""
    a, b = _rng(p.get("date_from"), p.get("date_to"))
    sales, sources = ZERO, {"day_close_pos_total": 0, "item_sales_report": 0}
    closes = {d.business_date: d for d in db.query(DayClose).all() if _in(d.business_date, a, b) and d.pos_total_sales is not None}
    report_days = defaultdict(lambda: ZERO)
    for l in db.query(ItemSaleLine).filter(ItemSaleLine.active.is_(True)):
        if _in(l.business_date, a, b):
            report_days[l.business_date] += l.amount
    for d in set(closes) | set(report_days):
        if d in closes:
            sales += closes[d].pos_total_sales
            sources["day_close_pos_total"] += 1
        else:
            sales += report_days[d]
            sources["item_sales_report"] += 1
    rows = [{"section": "Income", "line": "Sales (POS)", "amount": sales,
             "basis": f"{sources['day_close_pos_total']} day(s) from POS totals at day close, {sources['item_sales_report']} from Item Sales reports"}]
    by_cat = defaultdict(lambda: ZERO)
    for e in _expenses(db, p):
        by_cat[e.category] += e.total
    exp_total = ZERO
    for cat, amt in sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True):
        rows.append({"section": "Expenses", "line": cat, "amount": amt, "basis": "expenses incurred (paid or not)"})
        exp_total += amt
    net = sales - exp_total
    rows.append({"section": "Result", "line": "Operating profit (estimate)", "amount": net,
                 "basis": "sales − expenses; excludes stock valuation, depreciation, taxes"})
    return _tbl("Profit & Loss (operational estimate)", ["section", "line", "amount", "basis"], rows,
                {"sales": sales, "expenses": exp_total, "operating_profit": net})


REPORTS = {
    "customer-outstanding": customer_outstanding, "customer-statement": customer_statement,
    "udhari-collections": udhari_collections, "bill-outstanding": bill_outstanding,
    "expense-summary": expense_summary, "unpaid-expenses": unpaid_expenses, "paid-by-source": paid_by_source,
    "owner-ledger": owner_ledger_report, "cashbook": cashbook, "daily-closing": daily_closing,
    "item-sales-summary": item_sales_summary, "purchase-summary": purchase_summary,
    "stock-movements": stock_movements, "import-history": import_history,
    "customer-aging": customer_aging, "pnl-summary": pnl_summary,
}


def to_csv(rep: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(rep["columns"])
    for r in rep["rows"]:
        w.writerow(["" if r.get(c) is None else str(r.get(c)) for c in rep["columns"]])
    if rep["totals"]:
        w.writerow([])
        for k, v in rep["totals"].items():
            w.writerow(["TOTAL " + k, str(v)])
    return buf.getvalue()
