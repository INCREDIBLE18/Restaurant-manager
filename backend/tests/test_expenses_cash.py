from conftest import D
from test_udhari import acct_balance, mk_bill, mk_customer


def mk_expense(api, total="2000", **kw):
    r = api.post("/expenses", {"category": "Gas", "total": total, "expense_date": "2026-10-01", "description": "cylinder", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def pay(api, eid, amount, method="cash", funded="account", acct=None, **kw):
    return api.post(f"/expenses/{eid}/payments", {"amount": amount, "method": method, "funded_by": funded, "account_id": acct,
                                                  "paid_date": "2026-10-01", **kw})


def test_10_to_13_owner_funding_flow(admin, accts):
    e = mk_expense(admin)
    assert e["status"] == "unpaid" and D(e["due"]) == 2000
    assert acct_balance(admin, accts["Cash Drawer"]) == 0
    r = pay(admin, e["id"], "1000", acct=accts["Cash Drawer"])
    assert r.status_code == 200 and D(r.json()["due"]) == 1000 and r.json()["status"] == "partial"
    assert acct_balance(admin, accts["Cash Drawer"]) == -1000
    r = pay(admin, e["id"], "1000", funded="owner", paid_by="Owner")
    assert r.status_code == 200 and r.json()["status"] == "paid"
    assert acct_balance(admin, accts["Cash Drawer"]) == -1000  # owner money did not touch the drawer
    ob = admin.get("/owner/ledger").json()["balance"]
    assert D(ob["due_to_owner"]) == 1000
    n_expenses = len(admin.get("/expenses").json())
    r = admin.post("/owner/reimburse", {"amount": "1000", "method": "cash", "account_id": accts["Cash Drawer"], "paid_date": "2026-10-02"})
    assert r.status_code == 200
    assert acct_balance(admin, accts["Cash Drawer"]) == -2000
    assert D(admin.get("/owner/ledger").json()["balance"]["due_to_owner"]) == 0
    assert len(admin.get("/expenses").json()) == n_expenses  # reimbursement is not a new expense
    assert admin.post("/owner/reimburse", {"amount": "1", "method": "cash", "account_id": accts["Cash Drawer"]}).status_code == 422


def test_non_reimbursable_contribution(admin):
    e = mk_expense(admin, "500")
    pay(admin, e["id"], "500", funded="owner", reimbursable=False)
    b = admin.get("/owner/ledger").json()["balance"]
    assert D(b["due_to_owner"]) == 0 and D(b["contributions"]) == 500


def test_14_negative_and_overpayment_rejected(admin, accts):
    assert admin.post("/expenses", {"category": "X", "total": "-5"}).status_code == 422
    e = mk_expense(admin, "100")
    assert pay(admin, e["id"], "-1", acct=accts["Cash Drawer"]).status_code == 422
    assert pay(admin, e["id"], "0", acct=accts["Cash Drawer"]).status_code == 422
    assert pay(admin, e["id"], "150", acct=accts["Cash Drawer"]).status_code == 422
    assert acct_balance(admin, accts["Cash Drawer"]) == 0


def test_15_upi_expense_not_drawer(admin, accts):
    e = mk_expense(admin, "300")
    assert pay(admin, e["id"], "300", method="upi", acct=accts["UPI"]).status_code == 200
    assert acct_balance(admin, accts["Cash Drawer"]) == 0 and acct_balance(admin, accts["UPI"]) == -300
    # UPI cannot be posted to the drawer account
    e2 = mk_expense(admin, "10")
    assert pay(admin, e2["id"], "10", method="upi", acct=accts["Cash Drawer"]).status_code == 422


def test_split_payments_and_void(admin, accts):
    e = mk_expense(admin, "1000")
    pay(admin, e["id"], "400", acct=accts["Cash Drawer"])
    p2 = pay(admin, e["id"], "600", method="bank", acct=accts["Bank Account"]).json()
    assert p2["status"] == "paid" and len(p2["payments"]) == 2
    v = admin.post(f"/expense-payments/{p2['payments'][1]['id']}/void", {"reason": "wrong account"})
    assert v.status_code == 200 and v.json()["status"] == "partial"
    assert acct_balance(admin, accts["Bank Account"]) == 0


def test_16_expected_cash_formula(admin, accts):
    cash = accts["Cash Drawer"]
    cid = mk_customer(admin)
    b = mk_bill(admin, cid, "A", "700").json()
    d = "2026-10-05"
    admin.post("/receipts", {"customer_id": cid, "amount": "700", "method": "cash", "account_id": cash, "receipt_date": d,
                             "allocations": [{"bill_id": b["id"], "amount": "700"}]})
    admin.post("/cash-movements", {"kind": "other_in", "account_id": cash, "amount": "100", "date": d, "note": "float top-up"})
    e = mk_expense(admin, "1200", expense_date=d)
    pay(admin, e["id"], "1200", acct=cash, paid_date=d)
    admin.post("/cash-movements", {"kind": "refund", "account_id": cash, "amount": "100", "date": d, "note": "refund"})
    r = admin.put(f"/day-closes/{d}", {"opening_cash": "2000", "cash_sales": "5000"})
    assert r.status_code == 200, r.text
    assert D(r.json()["expected_cash"]) == 6500  # 2000+5000+700+100-1200-100


def test_17_variance_no_auto_expense(admin, accts):
    d = "2026-10-05"
    n = len(admin.get("/expenses").json())
    admin.put(f"/day-closes/{d}", {"opening_cash": "2000", "cash_sales": "4500"})
    r = admin.post(f"/day-closes/{d}/finalize", {"physical_counted": "6400"})
    assert r.status_code == 422 and "reason" in r.text  # variance -100 >= threshold 50 needs a note
    r = admin.post(f"/day-closes/{d}/finalize", {"physical_counted": "6400", "variance_reason": "short change given"})
    assert r.status_code == 200 and D(r.json()["variance"]) == -100 and r.json()["status"] == "finalized"
    assert len(admin.get("/expenses").json()) == n
    assert admin.get("/cash-movements").json() == []


def test_18_upi_collection_not_in_drawer_expected(admin, accts):
    cid = mk_customer(admin)
    b = mk_bill(admin, cid, "U", "400").json()
    admin.post("/receipts", {"customer_id": cid, "amount": "400", "method": "upi", "account_id": accts["UPI"], "receipt_date": "2026-10-05",
                             "allocations": [{"bill_id": b["id"], "amount": "400"}]})
    r = admin.put("/day-closes/2026-10-05", {"opening_cash": "1000", "cash_sales": "0"})
    assert D(r.json()["expected_cash"]) == 1000 and D(r.json()["ledger"]["cash_udhari_collections"]) == 0
    assert acct_balance(admin, accts["UPI"]) == 400


def test_19_transfers_are_not_sales_or_expenses(admin, accts):
    n = len(admin.get("/expenses").json())
    r = admin.post("/transfers", {"from_account_id": accts["Cash Drawer"], "to_account_id": accts["Bank Account"], "amount": "1500", "date": "2026-10-05"})
    assert r.status_code == 200
    assert acct_balance(admin, accts["Cash Drawer"]) == -1500 and acct_balance(admin, accts["Bank Account"]) == 1500
    assert len(admin.get("/expenses").json()) == n
    r = admin.put("/day-closes/2026-10-05", {"opening_cash": "2000", "cash_sales": "0"}).json()
    assert D(r["ledger"]["transfers_out"]) == 1500 and D(r["expected_cash"]) == 500  # drawer physically lost the cash
    assert admin.post("/transfers", {"from_account_id": 1, "to_account_id": 1, "amount": "5"}).status_code == 422


def test_20_finalized_day_locked_admin_reopen(admin, staff, accts):
    d = "2026-10-06"
    admin.put(f"/day-closes/{d}", {"opening_cash": "100", "cash_sales": "0"})
    assert admin.post(f"/day-closes/{d}/finalize", {"physical_counted": "100"}).status_code == 200
    assert admin.put(f"/day-closes/{d}", {"opening_cash": "999"}).status_code == 409
    # posting into a finalized date is blocked
    r = admin.post("/cash-movements", {"kind": "other_in", "account_id": accts["Cash Drawer"], "amount": "10", "date": d, "note": "late"})
    assert r.status_code == 409
    assert staff.post(f"/day-closes/{d}/reopen", {"reason": "typo"}).status_code == 403  # test 31
    assert admin.post(f"/day-closes/{d}/reopen", {}).status_code == 422
    assert admin.post(f"/day-closes/{d}/reopen", {"reason": "count recheck"}).json()["status"] == "reopened"
    log = admin.get("/audit?entity_type=day_close").json()
    assert any(a["action"] == "reopen" and a["reason"] == "count recheck" and a["user"] == "owner" for a in log)


def test_opening_cash_carry_forward(admin):
    admin.put("/day-closes/2026-10-06", {"opening_cash": "100", "cash_sales": "50"})
    admin.post("/day-closes/2026-10-06/finalize", {"physical_counted": "150"})
    nxt = admin.get("/day-closes/2026-10-07").json()
    assert D(nxt["suggested_opening"]) == 150 and D(nxt["opening_cash"]) == 150
