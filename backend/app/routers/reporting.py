from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from .. import backup as backup_mod
from .. import cash, ledger
from ..core import admin_user, audit, current_user, err, get_setting, today_ist
from ..db import get_db
from ..models import (
    Account, CashMovement, Customer, DayClose, Expense, ImportBatch, ImportRow, Item, ItemSaleLine, User,
)
from ..reports import REPORTS, to_csv
from . import stock as stock_router

router = APIRouter()
ZERO = Decimal("0")


@router.get("/reports")
def list_reports(_: User = Depends(current_user)):
    return sorted(REPORTS)


@router.get("/reports/{name}")
def run_report(name: str, request: Request, format: str = "json", db: Session = Depends(get_db), user: User = Depends(current_user)):
    fn = REPORTS.get(name)
    if not fn:
        err(404, "Unknown report")
    params = {k: v for k, v in request.query_params.items() if k != "format"}
    rep = fn(db, params)
    if format == "csv":
        audit(db, user, "export", "report", name, after=params)
        db.commit()
        return Response("﻿" + to_csv(rep), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    return rep


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(current_user)):
    today = today_ist()
    od = int(get_setting(db, "overdue_days") or 30)
    total_out, overdue_n, overdue_amt = ZERO, 0, ZERO
    for c in db.query(Customer):
        b = ledger.customer_balance(db, c.id)
        total_out += b["outstanding"]
        if b["oldest_open_bill_date"] and (today - today.fromisoformat(b["oldest_open_bill_date"])).days > od:
            overdue_n += 1
            overdue_amt += b["outstanding"]
    from ..models import Receipt
    collected_today = sum((r.amount for r in db.query(Receipt).filter(
        Receipt.receipt_date == today, Receipt.status == "posted", Receipt.kind == "collection")), ZERO)
    unpaid_n, unpaid_amt = 0, ZERO
    for e in db.query(Expense).filter(Expense.status == "posted"):
        s = ledger.expense_summary(db, e)
        if s["due"] > 0:
            unpaid_n += 1
            unpaid_amt += s["due"]
    exp_by_src = {}
    from ..models import ExpensePayment
    for p in db.query(ExpensePayment).filter(ExpensePayment.paid_date == today, ExpensePayment.status == "posted"):
        k = p.account.name if p.account else "Owner (personal funds)"
        exp_by_src[k] = exp_by_src.get(k, ZERO) + p.amount
    day = cash.compute(db, today)
    last = db.query(ImportBatch).filter(ImportBatch.report_type == "item_sales", ImportBatch.status == "confirmed") \
        .order_by(ImportBatch.report_date.desc()).first()
    last_sales = None
    if last:
        lines = db.query(ItemSaleLine).filter(ItemSaleLine.batch_id == last.id, ItemSaleLine.active.is_(True)).all()
        last_sales = {"report_date": last.report_date.isoformat(), "qty": sum((l.qty for l in lines), ZERO),
                      "amount": sum((l.amount for l in lines), ZERO), "note": "Item report data — not cash collected"}
    low = [s for s in (stock_router.inv.stock_view(db, i) for i in db.query(Item).filter(Item.track_stock.is_(True))) if s["below_threshold"]]
    drafts = db.query(ImportBatch).filter(ImportBatch.status == "draft").all()
    unresolved = sum(stock_router.batch_summary(db, b)["unresolved"] for b in drafts)
    dups = len([b for b in drafts if b.duplicate_of_id])
    return {
        "total_outstanding": total_out, "collected_today": collected_today,
        "overdue_customers": overdue_n, "overdue_amount": overdue_amt, "overdue_days_setting": od,
        "unpaid_expenses_count": unpaid_n, "unpaid_expenses_amount": unpaid_amt,
        "owner_due": ledger.owner_balance(db)["due_to_owner"], "expenses_today_by_source": exp_by_src,
        "expected_closing_cash": day["expected_cash"], "day_status": day["status"],
        "latest_item_sales": last_sales, "low_stock_items": low,
        "unresolved_import_rows": unresolved, "duplicate_warnings": dups, "draft_imports": len(drafts),
        "pending_catalogue_items": db.query(Item).filter(Item.pending.is_(True)).count(),
        "accounts": [{"name": a.name, "balance": ledger.account_balance(db, a), "physical_cash": a.is_physical_cash}
                     for a in db.query(Account).filter(Account.active.is_(True))],
        "today": today.isoformat(),
    }


# ---- backups (admin)
@router.get("/backups")
def backups(_: User = Depends(admin_user)):
    return backup_mod.list_backups()


@router.post("/backups")
def make_backup(db: Session = Depends(get_db), admin: User = Depends(admin_user)):
    info = backup_mod.create_backup()
    audit(db, admin, "backup", "backup", info["name"], after=info)
    db.commit()
    return info


@router.get("/backups/{name}")
def download_backup(name: str, _: User = Depends(admin_user)):
    p = backup_mod.backup_path(name)
    return FileResponse(p, filename=name)
