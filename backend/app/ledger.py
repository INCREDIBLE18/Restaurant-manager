"""Deterministic ledger calculations and posting. No AI, no UI logic."""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from .core import METHODS, assert_day_open, audit, err, get_setting, money, today_ist
from .models import (
    Account, BillAdjustment, CashMovement, Customer, Expense, ExpensePayment, OwnerLedgerEntry,
    Receipt, ReceiptAllocation, SaleBill, User,
)

ZERO = Decimal("0")


# ---------------------------------------------------------------- accounts / cashbook
def get_account(db: Session, account_id, method: str | None = None) -> Account:
    acc = db.get(Account, account_id) if account_id else None
    if not acc or not acc.active:
        err(422, "Select a valid, active account")
    if method:
        if method not in METHODS:
            err(422, f"Unknown payment method '{method}'")
        if method == "cash" and not acc.is_physical_cash:
            err(422, "Cash payments must use a physical cash account (e.g. Cash Drawer)")
        if method != "cash" and acc.is_physical_cash:
            err(422, f"A {method} payment cannot be posted to a physical cash account")
    return acc


def post_movement(db, account: Account, business_date: date, amount: Decimal, movement_type: str,
                  source_type="", source_id=None, note="", user: User | None = None, reversal_of=None) -> CashMovement:
    m = CashMovement(account_id=account.id, business_date=business_date, amount=amount,
                     movement_type=movement_type, source_type=source_type, source_id=source_id,
                     note=note, user_id=user.id if user else None,
                     reversal_of_id=reversal_of.id if reversal_of else None)
    db.add(m)
    return m


def reverse_movements(db, source_type: str, source_id: int, user: User | None, reason: str):
    """Create exact opposite movements (dated today) for every un-reversed movement of a source."""
    orig = db.query(CashMovement).filter(
        CashMovement.source_type == source_type, CashMovement.source_id == source_id,
        CashMovement.reversal_of_id.is_(None)).all()
    done = {m.reversal_of_id for m in db.query(CashMovement).filter(
        CashMovement.source_type == source_type, CashMovement.source_id == source_id,
        CashMovement.reversal_of_id.isnot(None)).all()}
    for m in orig:
        if m.id in done:
            continue
        db.add(CashMovement(
            account_id=m.account_id, business_date=today_ist(), amount=-m.amount,
            movement_type=m.movement_type + "_reversal", source_type=source_type, source_id=source_id,
            note=f"Reversal of movement #{m.id}: {reason}", user_id=user.id if user else None,
            reversal_of_id=m.id))


def account_balance(db: Session, acc: Account) -> Decimal:
    q = db.query(CashMovement).filter(CashMovement.account_id == acc.id)
    return acc.opening_balance + sum((m.amount for m in q), ZERO)


# ---------------------------------------------------------------- receivables
def active_alloc_total(bill: SaleBill) -> Decimal:
    return sum((a.amount for a in alloc_rows(bill) if a.active and a.receipt.status == "posted"), ZERO)


def alloc_rows(bill: SaleBill):
    from sqlalchemy.orm import object_session
    return object_session(bill).query(ReceiptAllocation).filter(ReceiptAllocation.bill_id == bill.id).all()


def bill_adjusted(db, bill_id: int) -> Decimal:
    return sum((a.amount for a in db.query(BillAdjustment).filter(
        BillAdjustment.bill_id == bill_id, BillAdjustment.active.is_(True))), ZERO)


def bill_summary(db: Session, bill: SaleBill) -> dict:
    allocs = db.query(ReceiptAllocation).filter(ReceiptAllocation.bill_id == bill.id, ReceiptAllocation.active.is_(True)).all()
    paid = sum((a.amount for a in allocs if a.receipt.status == "posted"), ZERO)
    adj = bill_adjusted(db, bill.id)
    outstanding = ZERO if bill.status != "posted" else max(ZERO, bill.total - paid - adj)
    return {
        "id": bill.id, "bill_no": bill.bill_no, "pos_bill_no": bill.pos_bill_no,
        "customer_id": bill.customer_id, "business_date": bill.business_date.isoformat(),
        "total": bill.total, "collected": paid, "adjusted": adj, "outstanding": outstanding,
        "paid_now": bill.paid_now, "in_pos_report": bill.in_pos_report,
        "count_as_new_sale": bill.count_as_new_sale,
        "status": bill.status if bill.status != "posted" else ("paid" if outstanding == 0 else ("partial" if paid > 0 else "open")),
        "record_status": bill.status, "notes": bill.notes, "attachment": bill.attachment,
        "age_days": (today_ist() - bill.business_date).days,
    }


def customer_bills(db: Session, customer_id: int, open_only=False):
    bills = db.query(SaleBill).filter(SaleBill.customer_id == customer_id, SaleBill.status == "posted") \
        .order_by(SaleBill.business_date, SaleBill.id).all()
    rows = [bill_summary(db, b) for b in bills]
    return [r for r in rows if r["outstanding"] > 0] if open_only else rows


def receipt_unallocated(db: Session, r: Receipt) -> Decimal:
    if r.status != "posted":
        return ZERO
    used = sum((a.amount for a in db.query(ReceiptAllocation).filter(
        ReceiptAllocation.receipt_id == r.id, ReceiptAllocation.active.is_(True))), ZERO)
    return r.amount - used


def customer_balance(db: Session, customer_id: int) -> dict:
    bills = customer_bills(db, customer_id)
    due = sum((b["outstanding"] for b in bills), ZERO)
    receipts = db.query(Receipt).filter(Receipt.customer_id == customer_id, Receipt.status == "posted").all()
    advance = sum((receipt_unallocated(db, r) for r in receipts), ZERO)
    oldest = min((b["business_date"] for b in bills if b["outstanding"] > 0), default=None)
    last_rc = max((r.receipt_date for r in receipts if r.kind == "collection"), default=None)
    return {"outstanding": due, "advance": advance, "net": due - advance,
            "oldest_open_bill_date": oldest, "last_collection": last_rc.isoformat() if last_rc else None,
            "open_bills": sum(1 for b in bills if b["outstanding"] > 0)}


def next_number(db: Session, prefix_key: str, model, col, default_prefix: str) -> str:
    prefix = get_setting(db, prefix_key) or default_prefix
    n = db.query(model).count() + 1
    while True:
        cand = f"{prefix}-{n:05d}"
        if not db.query(model).filter(col == cand).first():
            return cand
        n += 1


def suggest_allocation(db: Session, customer_id: int, amount: Decimal):
    left, out = amount, []
    for b in customer_bills(db, customer_id, open_only=True):
        if left <= 0:
            break
        a = min(left, b["outstanding"])
        out.append({"bill_id": b["id"], "amount": a})
        left -= a
    return {"allocations": out, "unallocated": left}


def create_receipt(db: Session, user: User, *, customer: Customer, amount: Decimal, receipt_date: date, method: str,
                   account_id, reference="", received_by="", notes="", allocations=None, auto_allocate=False,
                   kind="collection", post_to_cashbook=True, receipt_no=None) -> Receipt:
    acc = get_account(db, account_id, method)
    assert_day_open(db, receipt_date) if post_to_cashbook else None
    allocations = allocations or []
    if auto_allocate and not allocations:
        allocations = suggest_allocation(db, customer.id, amount)["allocations"]
    rc = Receipt(
        receipt_no=receipt_no or next_number(db, "receipt_prefix", Receipt, Receipt.receipt_no, "RC"),
        customer_id=customer.id, receipt_date=receipt_date, amount=amount, method=method, account_id=acc.id,
        reference=reference, received_by=received_by, notes=notes, kind=kind,
        post_to_cashbook=post_to_cashbook, created_by=user.id)
    db.add(rc)
    db.flush()
    apply_allocations(db, rc, customer, allocations, amount)
    if post_to_cashbook:
        post_movement(db, acc, receipt_date, amount, "receipt" if kind == "collection" else "bill_time_receipt",
                      "receipt", rc.id, f"{rc.receipt_no} from {customer.name}", user)
    audit(db, user, "create", "receipt", rc.id, after={"receipt_no": rc.receipt_no, "customer": customer.id, "amount": amount,
                                                         "method": method, "account": acc.name, "kind": kind})
    return rc


def apply_allocations(db, rc: Receipt, customer: Customer, allocations, receipt_amount: Decimal):
    """Validate + store allocations. Extra receipt money stays explicitly unallocated (customer advance)."""
    already = sum((a.amount for a in db.query(ReceiptAllocation).filter(
        ReceiptAllocation.receipt_id == rc.id, ReceiptAllocation.active.is_(True))), ZERO)
    total_new = ZERO
    seen = set()
    for a in allocations:
        bill = db.get(SaleBill, a["bill_id"], with_for_update=True)  # serialise concurrent allocations (PostgreSQL)
        amt = money(a["amount"], "allocation amount")
        if not bill or bill.customer_id != customer.id:
            err(422, "Allocation refers to a bill that does not belong to this customer")
        if bill.status != "posted":
            err(422, f"Bill {bill.bill_no} is not active")
        if bill.id in seen:
            err(422, "Duplicate bill in allocation list")
        seen.add(bill.id)
        out = bill_summary(db, bill)["outstanding"]
        if amt > out:
            err(422, f"Allocation ₹{amt} exceeds the open balance ₹{out} of bill {bill.bill_no}. "
                     "Leave the extra unallocated to record it as customer advance.")
        total_new += amt
        db.add(ReceiptAllocation(receipt_id=rc.id, bill_id=bill.id, amount=amt))
    if already + total_new > receipt_amount:
        err(422, "Allocations exceed the receipt amount")
    db.flush()


def void_receipt(db, user, rc: Receipt, reason: str):
    if rc.status != "posted":
        err(409, "Receipt is already voided")
    if not reason.strip():
        err(422, "A reason is required")
    rc.status, rc.void_reason = "voided", reason
    for a in db.query(ReceiptAllocation).filter(ReceiptAllocation.receipt_id == rc.id):
        a.active = False
    reverse_movements(db, "receipt", rc.id, user, reason)
    audit(db, user, "void", "receipt", rc.id, before={"amount": rc.amount, "status": "posted"},
          after={"status": "voided"}, reason=reason)


def create_bill(db: Session, user: User, *, customer: Customer, bill_no: str, pos_bill_no: str, business_date: date,
                total: Decimal, paid_now: Decimal, method=None, account_id=None, in_pos_report=True,
                count_as_new_sale=False, notes="", attachment="", lines=None, force_duplicate=False,
                post_paid_now=None) -> SaleBill:
    if paid_now > total:
        err(422, "Amount received now cannot exceed the bill total")
    if not bill_no.strip():
        err(422, "Bill number is required")
    dup = db.query(SaleBill).filter(SaleBill.bill_no == bill_no.strip(), SaleBill.status == "posted").first()
    if dup and not force_duplicate:
        err(409, f"Bill number '{bill_no}' already exists (customer #{dup.customer_id}). Tick 'allow duplicate' to save anyway.")
    if get_setting(db, "phone_mandatory") == "true" and not customer.phone.strip():
        err(422, "Customer phone is mandatory (see Settings)")
    if count_as_new_sale and in_pos_report:
        err(422, "A bill already included in the POS report cannot also be counted as a new sale")
    bill = SaleBill(bill_no=bill_no.strip(), pos_bill_no=pos_bill_no, customer_id=customer.id,
                    business_date=business_date, total=total, paid_now=paid_now, in_pos_report=in_pos_report,
                    count_as_new_sale=count_as_new_sale, notes=notes, attachment=attachment, created_by=user.id)
    db.add(bill)
    db.flush()
    from .models import SaleBillLine
    for ln in lines or []:
        lt = money(ln.get("line_total", 0), "line total", allow_zero=True)
        db.add(SaleBillLine(bill_id=bill.id, item_id=ln.get("item_id"), item_name=ln.get("item_name", ""),
                            quantity=ln.get("quantity", 1), unit=ln.get("unit", ""),
                            unit_price=ln.get("unit_price", 0), discount=ln.get("discount", 0), line_total=lt))
    audit(db, user, "create", "sale_bill", bill.id, after={"bill_no": bill.bill_no, "total": total,
                                                          "customer": customer.id, "in_pos_report": in_pos_report})
    if paid_now > 0:
        if post_paid_now is None:
            # A part-payment taken at the POS counter is already inside POS tender totals: do not
            # post it to the cashbook a second time unless the user explicitly asks.
            post_paid_now = not in_pos_report
        create_receipt(db, user, customer=customer, amount=paid_now, receipt_date=business_date,
                       method=method or "cash", account_id=account_id, notes=f"Paid at time of bill {bill.bill_no}",
                       allocations=[{"bill_id": bill.id, "amount": paid_now}], kind="bill_time",
                       post_to_cashbook=post_paid_now)
    return bill


def void_bill(db, user, bill: SaleBill, reason: str):
    if bill.status != "posted":
        err(409, "Bill already voided")
    if not reason.strip():
        err(422, "A reason is required")
    others = db.query(ReceiptAllocation).join(Receipt).filter(
        ReceiptAllocation.bill_id == bill.id, ReceiptAllocation.active.is_(True),
        Receipt.status == "posted", Receipt.kind != "bill_time").count()
    if others:
        err(409, "This bill has collections allocated to it. Void those receipts first.")
    for rc in db.query(Receipt).join(ReceiptAllocation).filter(
            ReceiptAllocation.bill_id == bill.id, Receipt.kind == "bill_time", Receipt.status == "posted"):
        void_receipt(db, user, rc, f"Bill {bill.bill_no} voided: {reason}")
    bill.status, bill.void_reason = "voided", reason
    audit(db, user, "void", "sale_bill", bill.id, before={"status": "posted"}, after={"status": "voided"}, reason=reason)


# ---------------------------------------------------------------- expenses
def expense_summary(db: Session, e: Expense) -> dict:
    pays = db.query(ExpensePayment).filter(ExpensePayment.expense_id == e.id, ExpensePayment.status == "posted").all()
    paid = sum((p.amount for p in pays), ZERO)
    due = max(ZERO, e.total - paid) if e.status == "posted" else ZERO
    status = "voided" if e.status != "posted" else ("paid" if due == 0 else ("partial" if paid > 0 else "unpaid"))
    last = max((p.paid_date for p in pays), default=None)
    return {
        "id": e.id, "expense_date": e.expense_date.isoformat(), "category": e.category,
        "description": e.description, "vendor_id": e.vendor_id,
        "payee_name": e.payee_name or (e.vendor.name if e.vendor else ""), "bill_ref": e.bill_ref,
        "total": e.total, "paid": paid, "due": due, "status": status,
        "due_date": e.due_date.isoformat() if e.due_date else None,
        "overdue": bool(e.due_date and due > 0 and e.due_date < today_ist()),
        "last_payment_date": last.isoformat() if last else None, "attachment": e.attachment,
        "notes": e.notes, "purchase_bill_id": e.purchase_bill_id,
        "sources": sorted({(p.account.name if p.account else "Owner (personal funds)") for p in pays}),
        "paid_by": sorted({p.paid_by for p in pays if p.paid_by}),
    }


def add_expense_payment(db, user, e: Expense, *, amount: Decimal, paid_date: date, method: str, funded_by: str,
                        account_id=None, paid_by="", payee="", reference="", notes="", reimbursable=True):
    db.get(Expense, e.id, with_for_update=True, populate_existing=True)
    if e.status != "posted":
        err(409, "Expense is voided")
    due = expense_summary(db, e)["due"]
    if amount > due:
        err(422, f"Payment ₹{amount} exceeds the remaining payable ₹{due}")
    if method not in METHODS:
        err(422, f"Unknown payment method '{method}'")
    p = ExpensePayment(expense_id=e.id, amount=amount, paid_date=paid_date, method=method, funded_by=funded_by,
                       paid_by=paid_by, payee=payee or e.payee_name, reference=reference, notes=notes, created_by=user.id)
    if funded_by == "owner":
        # Owner's personal money: expense recorded once, no restaurant account movement.
        p.account_id = None
        p.paid_by = paid_by or "Owner"
        db.add(p)
        db.flush()
        db.add(OwnerLedgerEntry(entry_date=paid_date, kind="funded" if reimbursable else "contribution",
                                amount=amount, expense_payment_id=p.id, method=method,
                                note=f"Expense #{e.id} {e.category}", created_by=user.id))
    elif funded_by == "account":
        acc = get_account(db, account_id, method)
        assert_day_open(db, paid_date)
        p.account_id = acc.id
        db.add(p)
        db.flush()
        post_movement(db, acc, paid_date, -amount, "expense_payment", "expense_payment", p.id,
                      f"Expense #{e.id} {e.category}", user)
    else:
        err(422, "funded_by must be 'account' or 'owner'")
    audit(db, user, "create", "expense_payment", p.id, after={"expense": e.id, "amount": amount, "funded_by": funded_by,
                                                             "method": method})
    return p


def void_expense_payment(db, user, p: ExpensePayment, reason: str):
    if p.status != "posted":
        err(409, "Payment already voided")
    if not reason.strip():
        err(422, "A reason is required")
    p.status, p.void_reason = "voided", reason
    reverse_movements(db, "expense_payment", p.id, user, reason)
    for o in db.query(OwnerLedgerEntry).filter(OwnerLedgerEntry.expense_payment_id == p.id):
        o.active = False
    audit(db, user, "void", "expense_payment", p.id, before={"amount": p.amount}, after={"status": "voided"}, reason=reason)


def owner_balance(db: Session) -> dict:
    rows = db.query(OwnerLedgerEntry).filter(OwnerLedgerEntry.active.is_(True)).all()
    funded = sum((r.amount for r in rows if r.kind == "funded"), ZERO)
    reimb = sum((r.amount for r in rows if r.kind == "reimbursement"), ZERO)
    contrib = sum((r.amount for r in rows if r.kind == "contribution"), ZERO)
    return {"owner_funded": funded, "reimbursed": reimb, "contributions": contrib, "due_to_owner": funded - reimb}


def reimburse_owner(db, user, amount: Decimal, paid_date: date, method: str, account_id, note=""):
    bal = owner_balance(db)["due_to_owner"]
    if amount > bal:
        err(422, f"Reimbursement ₹{amount} exceeds the amount due to owner ₹{bal}")
    acc = get_account(db, account_id, method)
    assert_day_open(db, paid_date)
    ent = OwnerLedgerEntry(entry_date=paid_date, kind="reimbursement", amount=amount, account_id=acc.id,
                           method=method, note=note, created_by=user.id)
    db.add(ent)
    db.flush()
    post_movement(db, acc, paid_date, -amount, "owner_reimbursement", "owner_ledger", ent.id, note or "Owner reimbursement", user)
    audit(db, user, "create", "owner_reimbursement", ent.id, after={"amount": amount, "account": acc.name})
    return ent
