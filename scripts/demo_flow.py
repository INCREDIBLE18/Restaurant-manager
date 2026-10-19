"""DEMO DATA SEEDER — adds clearly fake demo records through the public API.

NEVER run this against your live database. Start a throw-away instance first, e.g.
    $env:DATABASE_URL="sqlite:///D:/path/demo.db"; alembic upgrade head; uvicorn app.main:app --port 8000
then:
    python scripts/demo_flow.py --base http://127.0.0.1:8000 --username owner --password <admin password> --i-understand-this-adds-demo-data

It walks the documented demo sequence: customer -> udhari bill -> partial payment -> settle -> unpaid expense ->
pay from two sources -> upload/review Item Sales PDF -> purchase -> close cash -> export reports.
"""
import argparse
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--username", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--date", default="2026-09-30")
    ap.add_argument("--skip-pdf", action="store_true", help="skip the slow OCR PDF import step")
    ap.add_argument("--i-understand-this-adds-demo-data", action="store_true")
    a = ap.parse_args()
    if not a.i_understand_this_adds_demo_data:
        sys.exit("Refusing to run: pass --i-understand-this-adds-demo-data (this writes DEMO records).")

    c = httpx.Client(base_url=a.base + "/api/v1", timeout=900)
    tok = c.post("/auth/login", json={"username": a.username, "password": a.password}).raise_for_status().json()["token"]
    c.headers["Authorization"] = f"Bearer {tok}"

    def call(method, url, **kw):
        r = c.request(method, url, **kw)
        if r.status_code >= 400:
            sys.exit(f"FAILED {method} {url}: {r.status_code} {r.text}")
        return r.json()

    accts = {x["name"]: x["id"] for x in call("GET", "/accounts")}
    cash, upi = accts["Cash Drawer"], accts["UPI"]
    d = a.date
    print("1. customer + udhari bill ₹1,200 (DEMO)")
    cust = call("POST", "/customers", json={"name": "DEMO Customer Ramesh", "phone": "9000000001"})
    bill = call("POST", "/credit-bills", json={"customer_id": cust["id"], "bill_no": "DEMO-1001", "total": "1200", "business_date": d, "in_pos_report": True})
    print("2. partial payment ₹500 cash")
    call("POST", "/receipts", json={"customer_id": cust["id"], "amount": "500", "method": "cash", "account_id": cash, "receipt_date": d,
                                    "allocations": [{"bill_id": bill["id"], "amount": "500"}], "received_by": "Cashier"})
    print("3. settle remaining ₹700 by UPI")
    call("POST", "/receipts", json={"customer_id": cust["id"], "amount": "700", "method": "upi", "account_id": upi, "receipt_date": d, "auto_allocate": True, "reference": "DEMO-UPI-1"})
    print("   outstanding now:", call("GET", f"/customers/{cust['id']}")["outstanding"])
    print("4. unpaid expense ₹2,000, paid ₹1,000 cash + ₹1,000 by owner personally")
    e = call("POST", "/expenses", json={"expense_date": d, "category": "Gas", "description": "DEMO cylinder refill", "total": "2000"})
    call("POST", f"/expenses/{e['id']}/payments", json={"amount": "1000", "method": "cash", "funded_by": "account", "account_id": cash, "paid_date": d, "paid_by": "Manager"})
    call("POST", f"/expenses/{e['id']}/payments", json={"amount": "1000", "method": "upi", "funded_by": "owner", "paid_date": d, "paid_by": "Owner"})
    print("   owner due:", call("GET", "/owner/ledger")["balance"]["due_to_owner"])
    if not a.skip_pdf:
        print("5. upload Item Sales PDF (local OCR can take a few minutes) …")
        pdf = ROOT / "reference_pdfs" / "Item Sales.PDF.pdf"
        t = time.time()
        with open(pdf, "rb") as fh:
            b = call("POST", "/imports/preview", data={"report_type": "item_sales", "report_date": ""}, files={"file": (pdf.name, fh, "application/pdf")})
        print(f"   read in {time.time()-t:.0f}s via {b['extraction_method']}: {b['summary']['item_rows']} item rows, "
              f"printed total {b['summary']['printed_total']}, accepted {b['summary']['accepted_amount']}, flagged {b['summary']['needs_review']}")
        for w in b["warnings"]:
            print("   WARNING:", w)
        print("   -> review rows in the app (Inventory & PDF Imports), fix flagged digits, map items, then Confirm import.")
        print(f"   draft batch id: {b['id']} (left unconfirmed on purpose: confirmation is a human decision)")
    print("6. purchase (DEMO supplier, untracked free-text line)")
    v = call("POST", "/vendors", json={"name": "DEMO Supplier"})
    call("POST", "/purchases", json={"vendor_id": v["id"], "invoice_no": "DEMO-INV-1", "invoice_date": d,
                                      "lines": [{"description": "Cooking oil 15L", "quantity": "2", "unit": "tin", "unit_price": "1800"}]})
    print("7. close cash for the day")
    call("PUT", f"/day-closes/{d}", json={"opening_cash": "2000", "cash_sales": "5000", "pos_total_sales": "9000", "upi_sales": "3000", "credit_sales": "1000"})
    info = call("GET", f"/day-closes/{d}")
    print("   expected cash:", info["expected_cash"])
    call("POST", f"/day-closes/{d}/finalize", json={"physical_counted": info["expected_cash"]})
    print("8. export a report")
    r = c.get("/reports/udhari-collections", params={"format": "csv"})
    print("   CSV bytes:", len(r.content))
    print("DONE — demo sequence completed.")


if __name__ == "__main__":
    main()
