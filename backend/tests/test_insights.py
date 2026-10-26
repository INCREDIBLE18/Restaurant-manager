from conftest import D
from test_udhari import mk_bill, mk_customer


def test_insights_aging_trend_and_activity(admin, accts):
    cid = mk_customer(admin, "Aging Cust", "5")
    mk_bill(admin, cid, "OLD", "1000", business_date="2026-01-01")
    b = mk_bill(admin, cid, "NEW", "300", business_date=__import__("app.core", fromlist=["today_ist"]).today_ist().isoformat()).json()
    admin.post("/receipts", {"customer_id": cid, "amount": "100", "method": "cash", "account_id": accts["Cash Drawer"],
                             "allocations": [{"bill_id": b["id"], "amount": "100"}]})
    r = admin.get("/dashboard/insights").json()
    ag = {x["bucket"]: D(x["amount"]) for x in r["aging"]}
    assert ag["0-30"] == 200 and ag["90+"] == 1000
    assert r["top_debtors"][0]["name"] == "Aging Cust" and D(r["top_debtors"][0]["outstanding"]) == 1200
    assert len(r["trend"]) == 14 and D(r["trend"][-1]["collections"]) == 100
    assert any(a["label"] == "Payment received" for a in r["recent_activity"])


def test_global_search(admin):
    cid = mk_customer(admin, "Ganesh Traders", "98765")
    mk_bill(admin, cid, "GX-77", "500")
    res = admin.get("/search?q=GX-7").json()["results"]
    assert res[0]["type"] == "bill" and res[0]["url"] == f"/udhari/{cid}"
    assert admin.get("/search?q=98765").json()["results"][0]["title"] == "Ganesh Traders"
    assert admin.get("/search?q=a").json()["results"] == []


def test_aging_and_pnl_reports(admin, accts):
    cid = mk_customer(admin)
    mk_bill(admin, cid, "A1", "700", business_date="2026-01-01")
    rep = admin.get("/reports/customer-aging").json()
    assert D(rep["totals"]["90+"]) == 700 and D(rep["totals"]["total"]) == 700
    admin.post("/expenses", {"category": "Gas", "total": "400", "expense_date": "2026-10-05"})
    admin.put("/day-closes/2026-10-05", {"opening_cash": "0", "cash_sales": "0", "pos_total_sales": "5000"})
    pnl = admin.get("/reports/pnl-summary?date_from=2026-10-01&date_to=2026-10-31").json()
    assert D(pnl["totals"]["sales"]) == 5000 and D(pnl["totals"]["expenses"]) == 400 and D(pnl["totals"]["operating_profit"]) == 4600


def test_attachments_stored_in_database(admin, db):
    from app.models import StoredFile
    r = admin.c.post("/api/v1/attachments", headers=admin.h, files={"file": ("bill.pdf", b"%PDF-1.4 data", "application/pdf")})
    name = r.json()["attachment"]
    assert db.get(StoredFile, name).size == len(b"%PDF-1.4 data")
    got = admin.c.get(f"/api/v1/attachments/{name}", headers=admin.h)
    assert got.status_code == 200 and got.content == b"%PDF-1.4 data" and got.headers["content-type"] == "application/pdf"


def test_health_has_no_deployment_details(client):
    body = client.get("/api/v1/health").json()
    assert set(body) == {"status", "database"}
