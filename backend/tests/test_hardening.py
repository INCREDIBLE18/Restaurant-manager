from conftest import D
from test_imports_inventory import csv_bytes, upload


def test_login_throttling(client, admin):
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"username": "owner", "password": "wrong-password"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"username": "owner", "password": "password123"})
    assert r.status_code == 429  # locked even with the right password
    from app.routers import auth
    auth._FAILS.clear()
    assert client.post("/api/v1/auth/login", json={"username": "owner", "password": "password123"}).status_code == 200


def test_security_headers(client):
    r = client.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_ai_import_is_draft_only_and_flagged(admin, monkeypatch):
    from app import ai, parsing
    monkeypatch.setattr(ai, "enabled", lambda: True)
    monkeypatch.setattr(parsing, "render_png_pages", lambda d, f: [b"x"])
    payload = {"report_type": "item_sales", "business_date": "2026-09-30", "rows": [
        {"raw_item_name": "Red Bull", "qty_sold": "3", "total_amount_inr": "450", "row_type": "item", "page_number": 1, "confidence": 0.9}]}
    monkeypatch.setattr(ai, "extract_item_sales", lambda pages: parsing.validate_ai_item_sales(payload))
    r = admin.c.post("/api/v1/imports/preview", headers=admin.h, data={"report_type": "item_sales", "use_ai": "true"},
                     files={"file": ("r.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["extraction_method"] == "ai" and b["status"] == "draft" and b["summary"]["needs_review"] == 1
    assert admin.get("/items").json() == []  # nothing committed from AI output
    assert admin.post(f"/imports/{b['id']}/confirm", {}).status_code == 422  # unmapped + unacknowledged


def test_ai_malformed_output_rejected_cleanly(admin, monkeypatch):
    from app import ai, parsing
    monkeypatch.setattr(ai, "enabled", lambda: True)
    monkeypatch.setattr(parsing, "render_png_pages", lambda d, f: [b"x"])
    def boom(pages):
        raise RuntimeError("AI extraction failed (ValueError); use local OCR / CSV / manual entry instead")
    monkeypatch.setattr(ai, "extract_item_sales", boom)
    r = admin.c.post("/api/v1/imports/preview", headers=admin.h, data={"report_type": "item_sales", "use_ai": "true"},
                     files={"file": ("r.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 422 and "AI extraction failed" in r.text
    assert admin.get("/imports").json() == []


def test_ai_disabled_refuses(admin, monkeypatch):
    from app import ai
    monkeypatch.setattr(ai, "enabled", lambda: False)
    r = admin.c.post("/api/v1/imports/preview", headers=admin.h, data={"report_type": "item_sales", "use_ai": "true"},
                     files={"file": ("r.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 422 and "not enabled" in r.text


def test_concurrent_receipts_cannot_overpay_a_bill(admin, accts):
    import threading
    from test_udhari import mk_bill, mk_customer, bal
    cid = mk_customer(admin)
    b = mk_bill(admin, cid, "RACE", "100").json()
    body = {"customer_id": cid, "amount": "100", "method": "cash", "account_id": accts["Cash Drawer"], "receipt_date": "2026-10-01",
            "allocations": [{"bill_id": b["id"], "amount": "100"}]}
    codes = []
    def go():
        codes.append(admin.post("/receipts", body).status_code)
    ts = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    ok = codes.count(200)
    # The bill must never be over-collected, whatever the interleaving: allocations in total <= bill total
    c = bal(admin, cid)
    collected = sum(D(x["collected"]) for x in c["bills"])
    assert collected <= 100 and D(c["outstanding"]) >= 0
    assert ok >= 1
