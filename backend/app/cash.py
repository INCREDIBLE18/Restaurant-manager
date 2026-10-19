"""Daily cash reconciliation. Expected cash is derived only from posted account movements
on physical-cash accounts plus operator-entered POS cash sales."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from .core import _jsonable, assert_day_open, audit, err, get_setting, money, today_ist
from .ledger import ZERO, post_movement, get_account
from .models import Account, CashMovement, DayClose, ItemSaleLine, ImportBatch, User, utcnow

# movement_type -> bucket in the closing formula
BUCKETS = {
    "receipt": "cash_udhari_collections", "receipt_reversal": "cash_udhari_collections",
    "bill_time_receipt": "cash_udhari_collections", "bill_time_receipt_reversal": "cash_udhari_collections",
    "other_in": "other_cash_in", "other_in_reversal": "other_cash_in",
    "transfer_in": "transfers_in", "transfer_in_reversal": "transfers_in",
    "expense_payment": "cash_expense_payments", "expense_payment_reversal": "cash_expense_payments",
    "owner_reimbursement": "owner_reimbursements", "owner_reimbursement_reversal": "owner_reimbursements",
    "refund": "cash_refunds", "refund_reversal": "cash_refunds",
    "withdrawal": "cash_withdrawals", "withdrawal_reversal": "cash_withdrawals",
    "other_out": "other_cash_out", "other_out_reversal": "other_cash_out",
    "transfer_out": "transfers_out", "transfer_out_reversal": "transfers_out",
}
INFLOWS = ["cash_udhari_collections", "other_cash_in", "transfers_in"]
OUTFLOWS = ["cash_expense_payments", "owner_reimbursements", "cash_refunds", "cash_withdrawals", "other_cash_out", "transfers_out"]


def ledger_lines(db: Session, d: date) -> dict:
    cash_ids = [a.id for a in db.query(Account).filter(Account.is_physical_cash.is_(True))]
    lines = {k: ZERO for k in INFLOWS + OUTFLOWS}
    unknown = ZERO
    if cash_ids:
        for m in db.query(CashMovement).filter(CashMovement.business_date == d, CashMovement.account_id.in_(cash_ids)):
            b = BUCKETS.get(m.movement_type)
            if b is None:
                unknown += m.amount
            elif b in INFLOWS:
                lines[b] += m.amount
            else:
                lines[b] += -m.amount  # outflow buckets shown as positive magnitudes
    if unknown:
        lines["other_cash_in"] += unknown  # never silently drop an unclassified movement
    return lines


def previous_closing(db: Session, d: date):
    prev = db.query(DayClose).filter(DayClose.business_date < d, DayClose.status == "finalized") \
        .order_by(DayClose.business_date.desc()).first()
    return prev


def compute(db: Session, d: date, dc: DayClose | None = None) -> dict:
    dc = dc or db.query(DayClose).filter(DayClose.business_date == d).first()
    lines = ledger_lines(db, d)
    prev = previous_closing(db, d)
    suggested_opening = prev.physical_counted if prev and prev.physical_counted is not None else None
    opening = dc.opening_cash if dc else (suggested_opening or ZERO)
    cash_sales = dc.cash_sales if dc else ZERO
    expected = opening + cash_sales + sum(lines[k] for k in INFLOWS) - sum(lines[k] for k in OUTFLOWS)
    counted = dc.physical_counted if dc else None
    variance = (counted - expected) if counted is not None else None

    warnings = []
    has_report = db.query(ImportBatch).filter(ImportBatch.report_type == "item_sales", ImportBatch.status == "confirmed",
                                              ImportBatch.report_date == d).first()
    if not has_report:
        warnings.append("No confirmed Item Sales report is imported for this date (closing is still allowed).")
    tender = None
    if dc and dc.pos_total_sales is not None:
        parts = [dc.cash_sales, dc.upi_sales or ZERO, dc.card_sales or ZERO, dc.other_sales or ZERO, dc.credit_sales or ZERO]
        tender = dc.pos_total_sales - sum(parts, ZERO)
        if tender != 0:
            warnings.append(f"POS tender components differ from POS total sales by ₹{tender} (entered figures; "
                            "refunds/discounts may explain it). Not auto-reconciled.")
    if suggested_opening is not None and opening != suggested_opening:
        warnings.append(f"Opening cash ₹{opening} differs from previous verified closing ₹{suggested_opening}; add an opening note.")
    return {
        "business_date": d.isoformat(), "status": dc.status if dc else "open",
        "opening_cash": opening, "suggested_opening": suggested_opening, "opening_note": dc.opening_note if dc else "",
        "cash_sales": cash_sales,
        "pos_total_sales": dc.pos_total_sales if dc else None, "upi_sales": dc.upi_sales if dc else None,
        "card_sales": dc.card_sales if dc else None, "other_sales": dc.other_sales if dc else None,
        "credit_sales": dc.credit_sales if dc else None, "tender_difference": tender,
        "ledger": lines,
        "expected_cash": expected, "physical_counted": counted, "variance": variance,
        "variance_reason": dc.variance_reason if dc else "",
        "finalized_at": dc.finalized_at.isoformat() if dc and dc.finalized_at else None,
        "reopen_reason": dc.reopen_reason if dc else "",
        "warnings": warnings, "note_threshold": get_setting(db, "variance_note_threshold"),
        "item_sales_report_imported": bool(has_report),
    }


def save_inputs(db: Session, user: User, d: date, data: dict) -> DayClose:
    dc = db.query(DayClose).filter(DayClose.business_date == d).first()
    if dc and dc.status == "finalized":
        err(409, "This day is finalized. An admin must reopen it first.")
    if not dc:
        dc = DayClose(business_date=d)
        db.add(dc)
    def m(k, allow_none=True):
        v = data.get(k)
        if v in (None, ""):
            return None
        return money(v, k, allow_zero=True)
    if "opening_cash" in data:
        dc.opening_cash = m("opening_cash") or ZERO
    dc.opening_note = data.get("opening_note", dc.opening_note or "")
    if "cash_sales" in data:
        dc.cash_sales = m("cash_sales") or ZERO
    for k in ("pos_total_sales", "upi_sales", "card_sales", "other_sales", "credit_sales", "physical_counted"):
        if k in data:
            setattr(dc, k, m(k))
    dc.variance_reason = data.get("variance_reason", dc.variance_reason or "")
    if dc.status == "reopened":
        pass
    db.flush()
    audit(db, user, "save", "day_close", d.isoformat(), after={k: data.get(k) for k in data})
    return dc


def finalize(db: Session, user: User, d: date, data: dict) -> DayClose:
    dc = save_inputs(db, user, d, data)
    if dc.physical_counted is None:
        err(422, "Enter the physical cash counted before finalizing")
    info = compute(db, d, dc)
    variance = info["variance"]
    threshold = Decimal(get_setting(db, "variance_note_threshold") or "0")
    if variance != 0 and abs(variance) >= threshold and not (dc.variance_reason or "").strip():
        err(422, f"Variance is ₹{variance}; a reason note is required at or above ₹{threshold}")
    prev = previous_closing(db, d)
    if prev and prev.physical_counted is not None and dc.opening_cash != prev.physical_counted and not (dc.opening_note or "").strip():
        err(422, f"Opening cash differs from the previous verified closing (₹{prev.physical_counted}); add an opening note")
    dc.expected_cash, dc.variance = info["expected_cash"], variance
    dc.snapshot = _jsonable({k: v for k, v in info.items() if k in ("ledger", "cash_sales", "opening_cash", "warnings")})
    dc.status, dc.finalized_by, dc.finalized_at = "finalized", user.id, utcnow()
    audit(db, user, "finalize", "day_close", d.isoformat(),
          after={"expected": info["expected_cash"], "counted": dc.physical_counted, "variance": variance})
    return dc


def reopen(db: Session, user: User, d: date, reason: str):
    dc = db.query(DayClose).filter(DayClose.business_date == d).first()
    if not dc or dc.status != "finalized":
        err(409, "Only a finalized day can be reopened")
    if not (reason or "").strip():
        err(422, "A reason is required to reopen a day")
    dc.status, dc.reopen_reason, dc.reopened_by, dc.reopened_at = "reopened", reason, user.id, utcnow()
    audit(db, user, "reopen", "day_close", d.isoformat(), before={"status": "finalized"}, after={"status": "reopened"}, reason=reason)
    return dc


def post_other_movement(db, user, *, kind: str, account_id, amount: Decimal, d: date, note: str, method="cash"):
    """other_in | other_out | refund | withdrawal."""
    if kind not in ("other_in", "other_out", "refund", "withdrawal"):
        err(422, "Invalid movement type")
    acc = get_account(db, account_id)
    assert_day_open(db, d)
    signed = amount if kind == "other_in" else -amount
    mv = post_movement(db, acc, d, signed, kind, "manual", None, note, user)
    audit(db, user, "create", "cash_movement", "new", after={"kind": kind, "amount": signed, "account": acc.name, "note": note})
    return mv


def transfer(db, user, *, from_id, to_id, amount: Decimal, d: date, note=""):
    if from_id == to_id:
        err(422, "Choose two different accounts")
    a, b = get_account(db, from_id), get_account(db, to_id)
    assert_day_open(db, d)
    out = post_movement(db, a, d, -amount, "transfer_out", "transfer", None, note or f"Transfer to {b.name}", user)
    inn = post_movement(db, b, d, amount, "transfer_in", "transfer", None, note or f"Transfer from {a.name}", user)
    audit(db, user, "create", "transfer", "new", after={"from": a.name, "to": b.name, "amount": amount})
    return out, inn
