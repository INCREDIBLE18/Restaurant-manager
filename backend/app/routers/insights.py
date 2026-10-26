"""Dashboard insights and global search (read-only, deterministic)."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import ledger
from ..core import current_user, today_ist
from ..db import get_db
from ..models import (
    AuditLog, Customer, DayClose, Expense, ExpensePayment, ItemSaleLine, Receipt, SaleBill, User, Vendor,
)

router = APIRouter()
ZERO = Decimal("0")
BUCKETS = [("0-30", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, 10 ** 6)]

ACTION_LABELS = {
    ("create", "sale_bill"): "Udhari bill added", ("create", "receipt"): "Payment received",
    ("void", "receipt"): "Receipt voided", ("void", "sale_bill"): "Bill voided",
    ("create", "expense"): "Expense added", ("create", "expense_payment"): "Expense paid",
    ("void", "expense_payment"): "Expense payment voided", ("create", "owner_reimbursement"): "Owner reimbursed",
    ("finalize", "day_close"): "Day closed", ("reopen", "day_close"): "Day reopened",
    ("confirm", "import_batch"): "Report imported", ("reverse", "import_batch"): "Import reversed",
    ("create", "customer"): "Customer added", ("create", "purchase"): "Purchase recorded",
    ("create", "transfer"): "Transfer", ("backup", "backup"): "Backup created",
}


def aging(db: Session):
    """Open udhari by age of each bill (not of the customer)."""
    today = today_ist()
    buckets = {k: ZERO for k, _, _ in BUCKETS}
    per_customer = defaultdict(lambda: {"outstanding": ZERO, "oldest": None})
    bills = db.query(SaleBill).filter(SaleBill.status == "posted").all()
    for b in bills:
        s = ledger.bill_summary(db, b)
        out = s["outstanding"]
        if out <= 0:
            continue
        age = (today - b.business_date).days
        for k, lo, hi in BUCKETS:
            if lo <= age <= hi:
                buckets[k] += out
                break
        pc = per_customer[b.customer_id]
        pc["outstanding"] += out
        pc["oldest"] = min(pc["oldest"] or b.business_date, b.business_date)
    return buckets, per_customer


@router.get("/dashboard/insights")
def insights(days: int = 14, db: Session = Depends(get_db), _: User = Depends(current_user)):
    days = max(7, min(days, 90))
    today = today_ist()
    start = today - timedelta(days=days - 1)
    buckets, per_customer = aging(db)
    names = {c.id: (c.name, c.phone) for c in db.query(Customer).filter(Customer.id.in_(list(per_customer) or [0]))}
    top = sorted(per_customer.items(), key=lambda kv: kv[1]["outstanding"], reverse=True)[:6]
    top_debtors = [{"customer_id": cid, "name": names.get(cid, ("?", ""))[0], "phone": names.get(cid, ("", ""))[1],
                    "outstanding": v["outstanding"], "oldest_days": (today - v["oldest"]).days} for cid, v in top]

    trend = {(start + timedelta(days=i)).isoformat(): {"collections": ZERO, "expenses": ZERO, "credit_given": ZERO, "item_sales": ZERO}
             for i in range(days)}
    for r in db.query(Receipt).filter(Receipt.status == "posted", Receipt.kind == "collection", Receipt.receipt_date >= start):
        k = r.receipt_date.isoformat()
        if k in trend:
            trend[k]["collections"] += r.amount
    for p in db.query(ExpensePayment).filter(ExpensePayment.status == "posted", ExpensePayment.paid_date >= start):
        k = p.paid_date.isoformat()
        if k in trend:
            trend[k]["expenses"] += p.amount
    for b in db.query(SaleBill).filter(SaleBill.status == "posted", SaleBill.business_date >= start):
        k = b.business_date.isoformat()
        if k in trend:
            trend[k]["credit_given"] += b.total - b.paid_now
    for l in db.query(ItemSaleLine).filter(ItemSaleLine.active.is_(True), ItemSaleLine.business_date >= start):
        k = l.business_date.isoformat()
        if k in trend:
            trend[k]["item_sales"] += l.amount

    recent = []
    for a in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(60):
        label = ACTION_LABELS.get((a.action, a.entity_type))
        if not label:
            continue
        amount = (a.after or {}).get("amount") or (a.after or {}).get("total") if isinstance(a.after, dict) else None
        recent.append({"ts": a.ts.isoformat(), "user": a.username, "label": label, "entity_type": a.entity_type,
                       "entity_id": a.entity_id, "amount": amount, "reason": a.reason})
        if len(recent) >= 10:
            break

    open_days = [d.business_date.isoformat() for d in db.query(DayClose).filter(DayClose.status != "finalized", DayClose.business_date < today)]
    last_closed = db.query(DayClose).filter(DayClose.status == "finalized").order_by(DayClose.business_date.desc()).first()
    due_soon = []
    for e in db.query(Expense).filter(Expense.status == "posted", Expense.due_date.isnot(None), Expense.due_date <= today + timedelta(days=7)):
        s = ledger.expense_summary(db, e)
        if s["due"] > 0:
            due_soon.append({"id": e.id, "payee": s["payee_name"] or e.category, "due": s["due"], "due_date": s["due_date"], "overdue": s["overdue"]})
    due_soon.sort(key=lambda x: x["due_date"])
    return {
        "aging": [{"bucket": k, "amount": buckets[k]} for k, _, _ in BUCKETS],
        "top_debtors": top_debtors,
        "trend": [{"date": k, **v} for k, v in trend.items()],
        "recent_activity": recent,
        "unclosed_days": open_days,
        "last_closed_day": last_closed.business_date.isoformat() if last_closed else None,
        "payables_due_soon": due_soon[:6],
    }


@router.get("/search")
def search(q: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    """One box to find customers, bills, receipts, expenses and suppliers."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"results": []}
    like = f"%{q}%"
    out = []
    for c in db.query(Customer).filter(or_(Customer.name.ilike(like), Customer.phone.ilike(like))).limit(6):
        out.append({"type": "customer", "id": c.id, "title": c.name, "subtitle": c.phone or "Customer", "url": f"/udhari/{c.id}"})
    for b in db.query(SaleBill).filter(or_(SaleBill.bill_no.ilike(like), SaleBill.pos_bill_no.ilike(like))).limit(5):
        out.append({"type": "bill", "id": b.id, "title": f"Bill {b.bill_no}", "subtitle": f"{b.customer.name} · ₹{b.total} · {b.business_date}",
                    "url": f"/udhari/{b.customer_id}"})
    for r in db.query(Receipt).filter(or_(Receipt.receipt_no.ilike(like), Receipt.reference.ilike(like))).limit(5):
        out.append({"type": "receipt", "id": r.id, "title": f"Receipt {r.receipt_no}", "subtitle": f"{r.customer.name} · ₹{r.amount} · {r.receipt_date}",
                    "url": f"/udhari/{r.customer_id}"})
    for e in db.query(Expense).filter(or_(Expense.description.ilike(like), Expense.payee_name.ilike(like),
                                          Expense.bill_ref.ilike(like), Expense.category.ilike(like))).limit(5):
        out.append({"type": "expense", "id": e.id, "title": f"{e.category}: {e.description or e.payee_name}"[:80],
                    "subtitle": f"₹{e.total} · {e.expense_date}", "url": f"/expenses?open={e.id}"})
    for v in db.query(Vendor).filter(Vendor.name.ilike(like)).limit(4):
        out.append({"type": "vendor", "id": v.id, "title": v.name, "subtitle": "Supplier", "url": f"/expenses?q={v.name}"})
    return {"results": out}
