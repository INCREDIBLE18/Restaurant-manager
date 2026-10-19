from conftest import D


def mk_customer(api, name="Customer A", phone="9999900001"):
    r = api.post("/customers", {"name": name, "phone": phone})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def mk_bill(api, cid, no, total, paid=0, acct=None, method="cash", **kw):
    body = {"customer_id": cid, "bill_no": no, "total": str(total), "paid_now": str(paid), "method": method,
            "account_id": acct, "business_date": "2026-09-30", **kw}
    return api.post("/credit-bills", body)


def bal(api, cid):
    return api.get(f"/customers/{cid}").json()


def acct_balance(api, aid):
    return D([a for a in api.get("/accounts").json() if a["id"] == aid][0]["balance"])


def test_01_to_03_partial_then_full(admin, accts):
    cid = mk_customer(admin)
    b = mk_bill(admin, cid, "B1", "1200").json()
    assert D(bal(admin, cid)["outstanding"]) == 1200
    r = admin.post("/receipts", {"customer_id": cid, "amount": "500", "method": "cash", "account_id": accts["Cash Drawer"],
                                 "receipt_date": "2026-10-01", "allocations": [{"bill_id": b["id"], "amount": "500"}]})
    assert r.status_code == 200, r.text
    assert D(bal(admin, cid)["outstanding"]) == 700
    assert acct_balance(admin, accts["Cash Drawer"]) == 500
    r = admin.post("/receipts", {"customer_id": cid, "amount": "700", "method": "upi", "account_id": accts["UPI"],
                                 "receipt_date": "2026-10-02", "auto_allocate": True})
    assert r.status_code == 200
    c = bal(admin, cid)
    assert D(c["outstanding"]) == 0 and c["bills"][0]["status"] == "paid"
    assert len(c["receipts"]) == 2
    assert acct_balance(admin, accts["UPI"]) == 700 and acct_balance(admin, accts["Cash Drawer"]) == 500


def test_04_oldest_first_suggestion(admin, accts):
    cid = mk_customer(admin)
    a = mk_bill(admin, cid, "A", "600", business_date="2026-09-01").json()
    b = mk_bill(admin, cid, "B", "900", business_date="2026-09-10").json()
    s = admin.get(f"/receipts/suggest-allocation?customer_id={cid}&amount=1000").json()
    assert [(x["bill_id"], D(x["amount"])) for x in s["allocations"]] == [(a["id"], 600), (b["id"], 400)]
    admin.post("/receipts", {"customer_id": cid, "amount": "1000", "method": "cash", "account_id": accts["Cash Drawer"],
                             "receipt_date": "2026-10-01", "auto_allocate": True})
    bills = {x["bill_no"]: x for x in bal(admin, cid)["bills"]}
    assert D(bills["A"]["outstanding"]) == 0 and D(bills["B"]["outstanding"]) == 500


def test_05_overpayment_is_explicit_advance(admin, accts):
    cid = mk_customer(admin)
    mk_bill(admin, cid, "A", "1200")
    r = admin.post("/receipts", {"customer_id": cid, "amount": "1500", "method": "cash", "account_id": accts["Cash Drawer"],
                                 "receipt_date": "2026-10-01", "auto_allocate": True}).json()
    assert D(r["unallocated"]) == 300
    c = bal(admin, cid)
    assert D(c["outstanding"]) == 0 and D(c["advance"]) == 300


def test_06_07_allocation_validation(admin, accts):
    c1, c2 = mk_customer(admin, "C1", "1"), mk_customer(admin, "C2", "2")
    b1 = mk_bill(admin, c1, "X1", "500").json()
    b2 = mk_bill(admin, c2, "X2", "500").json()
    base = {"method": "cash", "account_id": accts["Cash Drawer"], "receipt_date": "2026-10-01"}
    r = admin.post("/receipts", {**base, "customer_id": c1, "amount": "100", "allocations": [{"bill_id": b2["id"], "amount": "100"}]})
    assert r.status_code == 422 and "does not belong" in r.text
    r = admin.post("/receipts", {**base, "customer_id": c1, "amount": "900", "allocations": [{"bill_id": b1["id"], "amount": "600"}]})
    assert r.status_code == 422 and "exceeds the open balance" in r.text
    # nothing was posted by the rejected attempts
    assert acct_balance(admin, accts["Cash Drawer"]) == 0
    assert D(bal(admin, c1)["outstanding"]) == 500


def test_08_void_receipt_reverses(admin, accts):
    cid = mk_customer(admin)
    b = mk_bill(admin, cid, "A", "1000").json()
    r = admin.post("/receipts", {"customer_id": cid, "amount": "400", "method": "cash", "account_id": accts["Cash Drawer"],
                                 "receipt_date": "2026-10-01", "allocations": [{"bill_id": b["id"], "amount": "400"}]}).json()
    assert D(bal(admin, cid)["outstanding"]) == 600
    v = admin.post(f"/receipts/{r['id']}/void", {"reason": "entered twice"})
    assert v.status_code == 200
    assert D(bal(admin, cid)["outstanding"]) == 1000
    assert acct_balance(admin, accts["Cash Drawer"]) == 0
    mv = admin.get("/cash-movements").json()
    assert len(mv) == 2 and {m["movement_type"] for m in mv} == {"receipt", "receipt_reversal"}  # history retained
    log = admin.get("/audit?entity_type=receipt").json()
    assert any(a["action"] == "void" and a["reason"] == "entered twice" for a in log)


def test_09_pos_bill_paid_now_does_not_double_count(admin, accts):
    cid = mk_customer(admin)
    # POS-included bill: ₹300 paid at counter is already in POS tender -> no cashbook posting by default
    b = mk_bill(admin, cid, "P1", "1000", paid=300, acct=accts["Cash Drawer"], in_pos_report=True).json()
    assert D(b["outstanding"]) == 700 and b["in_pos_report"] is True and b["count_as_new_sale"] is False
    assert acct_balance(admin, accts["Cash Drawer"]) == 0
    # cannot also be flagged as a new sale
    r = mk_bill(admin, cid, "P2", "100", in_pos_report=True, count_as_new_sale=True)
    assert r.status_code == 422
    # an app-only bill (not in POS) does post its paid-now amount
    mk_bill(admin, cid, "N1", "500", paid=200, acct=accts["Cash Drawer"], in_pos_report=False, count_as_new_sale=True)
    assert acct_balance(admin, accts["Cash Drawer"]) == 200


def test_cash_method_needs_cash_account_and_validation(admin, accts):
    cid = mk_customer(admin)
    mk_bill(admin, cid, "A", "500")
    base = {"customer_id": cid, "amount": "100", "receipt_date": "2026-10-01"}
    assert admin.post("/receipts", {**base, "method": "upi", "account_id": accts["Cash Drawer"]}).status_code == 422
    assert admin.post("/receipts", {**base, "method": "cash", "account_id": accts["UPI"]}).status_code == 422
    assert admin.post("/receipts", {**base, "amount": "-5", "method": "cash", "account_id": accts["Cash Drawer"]}).status_code == 422
    assert admin.post("/receipts", {**base, "amount": "abc", "method": "cash", "account_id": accts["Cash Drawer"]}).status_code == 422
    assert mk_bill(admin, cid, "Z", "0").status_code == 422
    assert mk_bill(admin, cid, "Z", "100", paid=200, acct=accts["Cash Drawer"]).status_code == 422
    assert mk_bill(admin, cid, "A", "100").status_code == 409  # duplicate bill number


def test_advance_can_be_applied_later(admin, accts):
    cid = mk_customer(admin)
    rc = admin.post("/receipts", {"customer_id": cid, "amount": "300", "method": "cash", "account_id": accts["Cash Drawer"],
                                  "receipt_date": "2026-10-01"}).json()
    assert D(rc["unallocated"]) == 300
    b = mk_bill(admin, cid, "L", "250").json()
    r = admin.post(f"/receipts/{rc['id']}/allocations", {"allocations": [{"bill_id": b["id"], "amount": "250"}]})
    assert r.status_code == 200 and D(r.json()["unallocated"]) == 50
    assert D(bal(admin, cid)["outstanding"]) == 0
    assert acct_balance(admin, accts["Cash Drawer"]) == 300  # no second cash movement


def test_customer_duplicate_warning_and_statement(admin, accts):
    cid = mk_customer(admin, "Ramesh", "98")
    assert admin.post("/customers", {"name": "ramesh", "phone": ""}).status_code == 409
    assert admin.post("/customers", {"name": "Ramesh", "phone": "", "allow_duplicate": True}).status_code == 200
    b = mk_bill(admin, cid, "S1", "1200").json()
    admin.post("/receipts", {"customer_id": cid, "amount": "500", "method": "cash", "account_id": accts["Cash Drawer"],
                             "receipt_date": "2026-10-01", "auto_allocate": True})
    st = admin.get(f"/customers/{cid}/ledger").json()
    assert [D(r["balance"]) for r in st["rows"]] == [1200, 700] and D(st["closing_balance"]) == 700


def test_writeoff_admin_only(admin, staff):
    cid = mk_customer(admin)
    b = mk_bill(admin, cid, "W", "500").json()
    assert staff.post(f"/credit-bills/{b['id']}/adjustments", {"kind": "writeoff", "amount": "100", "reason": "x"}).status_code == 403
    assert admin.post(f"/credit-bills/{b['id']}/adjustments", {"kind": "writeoff", "amount": "100", "reason": "goodwill"}).status_code == 200
    assert D(bal(admin, cid)["outstanding"]) == 400


def test_import_old_udhari_csv(admin, accts):
    import io
    def up(csv_text, dry):
        return admin.c.post(f"/api/v1/credit-bills/import-csv?dry_run={'true' if dry else 'false'}", headers=admin.h,
                            files={"file": ("old.csv", csv_text.encode(), "text/csv")})
    good = "customer,phone,bill_no,date,amount,paid\nSita,111,OLD-1,2026-08-01,1000,200\nSita,111,OLD-2,2026-08-10,500,0\nRam,222,OLD-3,2026-07-01,300,0\n"
    r = up(good, True).json()
    assert r["ok"] and not r["committed"] and admin.get("/customers").json() == []
    bad = good + "Ram,222,OLD-3,2026-07-01,300,0\nX,,OLD-9,31/12/2026,abc,0\n"
    r = up(bad, False).json()
    assert not r["ok"] and not r["committed"] and admin.get("/customers").json() == []  # all-or-nothing
    assert any("duplicate" in i for x in r["rows"] for i in x["issues"])
    r = up(good, False).json()
    assert r["committed"]
    cs = {c["name"]: c for c in admin.get("/customers").json()}
    assert D(cs["Sita"]["outstanding"]) == 1300 and D(cs["Ram"]["outstanding"]) == 300
    assert acct_balance(admin, accts["Cash Drawer"]) == 0  # no cash movements invented
    assert up(good, False).status_code == 200 and not up(good, False).json()["ok"]  # re-import blocked as duplicates
