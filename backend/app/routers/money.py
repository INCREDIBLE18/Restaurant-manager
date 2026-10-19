"""Expenses, vendors, owner funding, cashbook, transfers, day close."""
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import cash, ledger
from ..core import admin_user, audit, current_user, err, money, parse_date, today_ist
from ..db import get_db
from ..models import CashMovement, Expense, ExpensePayment, OwnerLedgerEntry, User, Vendor

router = APIRouter()


class ExpenseIn(BaseModel):
    expense_date: Optional[str] = None
    category: str
    description: str = ""
    vendor_id: Optional[int] = None
    payee_name: str = ""
    bill_ref: str = ""
    total: Any
    due_date: Optional[str] = None
    attachment: str = ""
    notes: str = ""
    # optional immediate payment(s) – each is validated like a normal payment
    payments: list[dict] = []


class PaymentIn(BaseModel):
    amount: Any
    paid_date: Optional[str] = None
    method: str = "cash"
    funded_by: str = "account"  # account | owner
    account_id: Optional[int] = None
    paid_by: str = ""
    payee: str = ""
    reference: str = ""
    notes: str = ""
    reimbursable: bool = True


@router.get("/vendors")
def vendors(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return [{"id": v.id, "name": v.name, "phone": v.phone, "active": v.active} for v in db.query(Vendor).order_by(Vendor.name)]


@router.post("/vendors")
def add_vendor(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    name = (body.get("name") or "").strip()
    if not name:
        err(422, "Vendor name required")
    ex = db.query(Vendor).filter(Vendor.name.ilike(name)).first()
    if ex:
        err(409, f"Vendor '{ex.name}' already exists (id {ex.id})")
    v = Vendor(name=name, phone=body.get("phone", ""), address=body.get("address", ""), notes=body.get("notes", ""))
    db.add(v)
    db.flush()
    audit(db, user, "create", "vendor", v.id, after={"name": name})
    db.commit()
    return {"id": v.id, "name": v.name}


def pay_out(p: ExpensePayment):
    return {"id": p.id, "expense_id": p.expense_id, "amount": p.amount, "paid_date": p.paid_date.isoformat(),
            "method": p.method, "funded_by": p.funded_by, "account_id": p.account_id,
            "account": p.account.name if p.account else "Owner (personal funds)", "paid_by": p.paid_by,
            "payee": p.payee, "reference": p.reference, "notes": p.notes, "status": p.status, "void_reason": p.void_reason}


@router.get("/expenses")
def expenses(status: str = "", category: str = "", vendor_id: Optional[int] = None, date_from: str = "", date_to: str = "",
             source: str = "", paid_by: str = "", q: str = "", db: Session = Depends(get_db), _: User = Depends(current_user)):
    qs = db.query(Expense).order_by(Expense.expense_date.desc(), Expense.id.desc())
    if category:
        qs = qs.filter(Expense.category == category)
    if vendor_id:
        qs = qs.filter(Expense.vendor_id == vendor_id)
    if date_from:
        qs = qs.filter(Expense.expense_date >= parse_date(date_from))
    if date_to:
        qs = qs.filter(Expense.expense_date <= parse_date(date_to))
    out = [ledger.expense_summary(db, e) for e in qs.limit(1000)]
    if status == "due":
        out = [e for e in out if e["status"] in ("unpaid", "partial")]
    elif status == "overdue":
        out = [e for e in out if e["overdue"]]
    elif status:
        out = [e for e in out if e["status"] == status]
    if source:
        out = [e for e in out if source in e["sources"]]
    if paid_by:
        out = [e for e in out if any(paid_by.lower() in p.lower() for p in e["paid_by"])]
    if q:
        out = [e for e in out if q.lower() in (e["description"] + e["payee_name"] + e["category"] + e["bill_ref"]).lower()]
    return out


@router.post("/expenses")
def add_expense(body: ExpenseIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    total = money(body.total, "expense total")
    if not body.category.strip():
        err(422, "Category is required")
    if body.vendor_id and not db.get(Vendor, body.vendor_id):
        err(422, "Unknown vendor")
    e = Expense(expense_date=parse_date(body.expense_date) if body.expense_date else today_ist(),
                category=body.category.strip(), description=body.description, vendor_id=body.vendor_id,
                payee_name=body.payee_name, bill_ref=body.bill_ref, total=total,
                due_date=parse_date(body.due_date) if body.due_date else None, attachment=body.attachment,
                notes=body.notes, created_by=user.id)
    db.add(e)
    db.flush()
    audit(db, user, "create", "expense", e.id, after={"category": e.category, "total": total})
    for p in body.payments:
        pi = PaymentIn(**p)
        _pay(db, user, e, pi)
    db.commit()
    return ledger.expense_summary(db, e)


def _pay(db, user, e: Expense, p: PaymentIn):
    return ledger.add_expense_payment(
        db, user, e, amount=money(p.amount, "payment amount"),
        paid_date=parse_date(p.paid_date) if p.paid_date else today_ist(), method=p.method, funded_by=p.funded_by,
        account_id=p.account_id, paid_by=p.paid_by, payee=p.payee, reference=p.reference, notes=p.notes,
        reimbursable=p.reimbursable)


@router.get("/expenses/{eid}")
def expense_detail(eid: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    e = db.get(Expense, eid)
    if not e:
        err(404, "Expense not found")
    pays = db.query(ExpensePayment).filter(ExpensePayment.expense_id == eid).order_by(ExpensePayment.id).all()
    return {**ledger.expense_summary(db, e), "payments": [pay_out(p) for p in pays]}


@router.post("/expenses/{eid}/payments")
def add_payment(eid: int, body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = db.get(Expense, eid)
    if not e:
        err(404, "Expense not found")
    _pay(db, user, e, body)
    db.commit()
    return expense_detail(eid, db, user)


@router.post("/expense-payments/{pid}/void")
def void_payment(pid: int, body: dict, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    p = db.get(ExpensePayment, pid)
    if not p:
        err(404, "Payment not found")
    ledger.void_expense_payment(db, admin, p, body.get("reason", ""))
    db.commit()
    return expense_detail(p.expense_id, db, admin)


@router.post("/expenses/{eid}/void")
def void_expense(eid: int, body: dict, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    e = db.get(Expense, eid)
    if not e:
        err(404, "Expense not found")
    if not (body.get("reason") or "").strip():
        err(422, "A reason is required")
    if ledger.expense_summary(db, e)["paid"] > 0:
        err(409, "Void the payments first")
    e.status, e.void_reason = "voided", body["reason"]
    audit(db, admin, "void", "expense", e.id, reason=body["reason"])
    db.commit()
    return ledger.expense_summary(db, e)


# ---- owner
@router.get("/owner/ledger")
def owner_ledger(db: Session = Depends(get_db), _: User = Depends(current_user)):
    rows = db.query(OwnerLedgerEntry).order_by(OwnerLedgerEntry.entry_date.desc(), OwnerLedgerEntry.id.desc()).all()
    return {"balance": ledger.owner_balance(db),
            "entries": [{"id": r.id, "date": r.entry_date.isoformat(), "kind": r.kind, "amount": r.amount,
                         "note": r.note, "active": r.active, "method": r.method} for r in rows]}


@router.post("/owner/reimburse")
def reimburse(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    ent = ledger.reimburse_owner(db, user, money(body.get("amount"), "amount"),
                                 parse_date(body["paid_date"]) if body.get("paid_date") else today_ist(),
                                 body.get("method", "cash"), body.get("account_id"), body.get("note", ""))
    db.commit()
    return {"id": ent.id, "balance": ledger.owner_balance(db)}


# ---- cashbook
def mv_out(m: CashMovement):
    return {"id": m.id, "account_id": m.account_id, "account": m.account.name, "business_date": m.business_date.isoformat(),
            "amount": m.amount, "movement_type": m.movement_type, "source_type": m.source_type, "source_id": m.source_id,
            "note": m.note, "reversal_of_id": m.reversal_of_id}


@router.get("/cash-movements")
def movements(account_id: Optional[int] = None, date_from: str = "", date_to: str = "", db: Session = Depends(get_db),
              _: User = Depends(current_user)):
    q = db.query(CashMovement).order_by(CashMovement.business_date.desc(), CashMovement.id.desc())
    if account_id:
        q = q.filter(CashMovement.account_id == account_id)
    if date_from:
        q = q.filter(CashMovement.business_date >= parse_date(date_from))
    if date_to:
        q = q.filter(CashMovement.business_date <= parse_date(date_to))
    return [mv_out(m) for m in q.limit(1000)]


@router.post("/cash-movements")
def add_movement(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not (body.get("note") or "").strip():
        err(422, "A note is required for manual cash movements")
    mv = cash.post_other_movement(db, user, kind=body.get("kind", ""), account_id=body.get("account_id"),
                                  amount=money(body.get("amount"), "amount"),
                                  d=parse_date(body["date"]) if body.get("date") else today_ist(), note=body.get("note", ""))
    db.commit()
    return mv_out(mv)


@router.post("/transfers")
def transfers(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    cash.transfer(db, user, from_id=body.get("from_account_id"), to_id=body.get("to_account_id"),
                  amount=money(body.get("amount"), "amount"),
                  d=parse_date(body["date"]) if body.get("date") else today_ist(), note=body.get("note", ""))
    db.commit()
    return {"ok": True}


# ---- day close
@router.get("/day-closes")
def day_closes(db: Session = Depends(get_db), _: User = Depends(current_user)):
    from ..models import DayClose
    return [{"business_date": d.business_date.isoformat(), "status": d.status, "expected_cash": d.expected_cash,
             "physical_counted": d.physical_counted, "variance": d.variance}
            for d in db.query(DayClose).order_by(DayClose.business_date.desc()).limit(120)]


@router.get("/day-closes/{d}")
def day_close_get(d: str, db: Session = Depends(get_db), _: User = Depends(current_user)):
    return cash.compute(db, parse_date(d))


@router.put("/day-closes/{d}")
def day_close_save(d: str, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    dd = parse_date(d)
    dc = cash.save_inputs(db, user, dd, body)
    db.commit()
    return cash.compute(db, dd, dc)


@router.post("/day-closes/{d}/finalize")
def day_close_finalize(d: str, body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    dd = parse_date(d)
    dc = cash.finalize(db, user, dd, body)
    db.commit()
    return cash.compute(db, dd, dc)


@router.post("/day-closes/{d}/reopen")
def day_close_reopen(d: str, body: dict, db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    dd = parse_date(d)
    dc = cash.reopen(db, admin, dd, body.get("reason", ""))
    db.commit()
    return cash.compute(db, dd, dc)
