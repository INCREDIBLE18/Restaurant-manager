import csv
import io

import pytest
from conftest import D

from app import parsing

SAMPLE_TEXT = """AARAVI, TITWALA
ITEM SALES
Date: Wednesday 30-Sep-2026
Print Date: 01/10/26 11:01 AM
Item Name Qty Total
Department: Kitchen 2 390
Category: Indian Soup 1 160
Chi Manchow Soup 1 160
Category: Chinese Starter 1 230
Chicken Lollipop 1 230
Department: Liquor 19 4,750
Category: Whisky 6 1,650
Imperial Blue 180ml 3 750
" 2 660
Sub Total 5 1,410
Dsp Black 180ml 1 240
Category: Beer 13 3,100
Tuborg Strong 650ml 13 3,100
GrandTotal: 21 5,140
xxx End Of Report xxx
"""


def test_21_22_23_classification():
    lines, meta = parsing.item_sales_lines_from_text(SAMPLE_TEXT)
    r = parsing.classify_item_sales(lines, meta, "pdf_text")
    assert r.report_date.isoformat() == "2026-09-30"
    items = [x for x in r.rows if x.row_type in ("item", "ditto")]
    names = [(x.name, x.qty, x.amount) for x in items]
    assert ("Chicken Lollipop", D(1), D(230)) in names  # test 21
    assert all(x.name not in ('"', "") for x in items)  # test 23
    ditto = [x for x in r.rows if x.row_type == "ditto"][0]
    assert ditto.name == "Imperial Blue 180ml" and ditto.amount == 660
    types = {x.raw_name: x.row_type for x in r.rows}
    assert types["Department: Kitchen"] == "heading" and types["Category: Whisky"] == "heading"
    assert types["Sub Total"] == "subtotal" and types["GrandTotal:"] == "grand_total"
    assert any(x.row_type == "end" for x in r.rows)  # test 22
    assert r.printed_total == 5140
    # reconciliation: item rows add up to the printed grand total
    assert sum(x.amount for x in items) == 5140 and sum(x.qty for x in items) == 21
    assert not r.warnings or all("Category" not in w for w in r.warnings)


def test_23_ditto_without_predecessor_flagged():
    lines = [parsing.RawLine(1, '"', {"qty": "2", "total": "100"})]
    r = parsing.classify_item_sales(lines, {"text": []}, "x")
    row = r.rows[0]
    assert row.row_type == "ditto" and row.name == "" and row.needs_review


def test_subtotal_mismatch_is_flagged():
    t = SAMPLE_TEXT.replace('" 2 660', '" 2 600')
    lines, meta = parsing.item_sales_lines_from_text(t)
    r = parsing.classify_item_sales(lines, meta, "t")
    assert any("Sub total mismatch" in x.notes for x in r.rows)
    assert any("Category" in w or "Department" in w for w in r.warnings)


def test_30_malformed_ai_output_rejected():
    for bad in (None, {}, {"report_type": "item_sales", "rows": "x"},
                {"report_type": "item_sales", "rows": [{"raw_item_name": "A", "qty_sold": "abc"}]},
                {"report_type": "item_sales", "rows": [{"raw_item_name": "A", "qty_sold": 5}]},
                {"report_type": "item_sales", "rows": [{"raw_item_name": "A", "row_type": "weird"}]}):
        with pytest.raises(ValueError):
            parsing.validate_ai_item_sales(bad)
    ok = parsing.validate_ai_item_sales({"report_type": "item_sales", "business_date": "2026-09-30", "rows": [
        {"raw_item_name": "Red Bull", "qty_sold": "3", "total_amount_inr": "450", "row_type": "item", "page_number": 1, "confidence": 0.9}]})
    assert all(x.needs_review for x in ok.rows) and any("AI" in w for w in ok.warnings)


def csv_bytes(rows, header=("Item Name", "Qty Sold", "Total Amount")):
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(header)
    w.writerows(rows)
    return b.getvalue().encode()


def upload(api, rtype, data, date="", name="r.csv"):
    return api.c.post("/api/v1/imports/preview", headers=api.h, data={"report_type": rtype, "report_date": date},
                      files={"file": (name, data, "text/csv")})


SALES_ROWS = [("Department: Liquor", 6, 1500), ("Category: Whisky", 6, 1500), ("Imperial Blue 180ml", 3, 750), ('"', 2, 660),
              ("Sub Total", 5, 1410), ("Dsp Black 180ml", 1, 90), ("GrandTotal:", 6, 1500), ("xxx End Of Report xxx", "", "")]


def test_preview_import_flow_and_unmapped_queue(admin):
    r = upload(admin, "item_sales", csv_bytes(SALES_ROWS), "2026-09-30")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["extraction_method"] == "csv" and b["report_date"] == "2026-09-30"
    items = [x for x in b["rows"] if x["row_type"] in ("item", "ditto")]
    assert [(x["name"], x["qty"], x["amount"]) for x in items][0][0] == "Imperial Blue 180ml"
    assert b["summary"]["unresolved"] == len(items) and b["summary"]["excluded_structural"] >= 4
    # test 26: unmapped rows block confirmation; nothing is posted
    c = admin.post(f"/imports/{b['id']}/confirm", {"acknowledge_warnings": True})
    assert c.status_code == 422 and "no item mapping" in c.text
    assert admin.get("/items").json() == [] and admin.get("/reports/item-sales-summary").json()["rows"] == []


def confirm_sales(admin, rows=SALES_ROWS, date="2026-09-30"):
    b = upload(admin, "item_sales", csv_bytes(rows), date).json()
    for x in b["rows"]:
        if x["row_type"] in ("item", "ditto"):
            assert admin.patch(f"/imports/{b['id']}/rows/{x['id']}", {"create_item": True}).status_code == 200
    return b, admin.post(f"/imports/{b['id']}/confirm", {"acknowledge_warnings": True})


def test_confirm_creates_pending_items_not_structural(admin):
    b, c = confirm_sales(admin)
    assert c.status_code == 200, c.text
    names = {i["name"] for i in admin.get("/items").json()}
    assert names == {"Imperial Blue 180ml", "Dsp Black 180ml"}  # no headings / subtotals / grand total / '"'
    assert all(i["pending"] and not i["track_stock"] for i in admin.get("/items").json())
    rep = admin.get("/reports/item-sales-summary").json()
    ib = [r for r in rep["rows"] if r["item"] == "Imperial Blue 180ml"][0]
    assert D(ib["qty_sold"]) == 5 and D(ib["amount"]) == 1410  # base row + ditto merged
    assert D(rep["totals"]["amount"]) == 1500
    assert admin.get("/inventory/movements").json() == []  # untracked items: no stock-out


def test_25_duplicate_import_not_duplicated(admin, staff):
    b, c = confirm_sales(admin)
    assert c.status_code == 200
    again = upload(admin, "item_sales", csv_bytes(SALES_ROWS), "2026-09-30").json()
    assert again["duplicate_of_id"] == b["id"] and any("DUPLICATE" in w for w in again["warnings"])
    # same date, different file -> also flagged
    other = upload(admin, "item_sales", csv_bytes(SALES_ROWS[:-2] + [("Soda", 1, 20)]), "2026-09-30").json()
    assert other["duplicate_of_id"] == b["id"]
    r = admin.post(f"/imports/{again['id']}/confirm", {"acknowledge_warnings": True})
    assert r.status_code == 409 and "DUPLICATE" in r.text
    assert staff.post(f"/imports/{again['id']}/confirm", {"override_duplicate": True, "acknowledge_warnings": True}).status_code == 403
    rep = admin.get("/reports/item-sales-summary").json()
    assert D(rep["totals"]["amount"]) == 1500  # unchanged


def test_24_stock_position_names_only(admin):
    data = csv_bytes([("Black Label 180ml", "Nos", -9, 0, 5, "", "", "", "", -14, "12.50"), ("Red Label 750ml", "Nos", -60, 0, 0, "", "", "", "", -60, "")],
                     header=("Item Name", "UOM", "Open", "Purchase", "Issued/Sale", "Damage", "Wastage", "Variance", "Return", "Closing", "ClgStk Value"))
    b = upload(admin, "stock_position", data).json()
    assert all(r["qty"] is None and r["amount"] is None for r in b["rows"])
    c = admin.post(f"/imports/{b['id']}/confirm", {"acknowledge_warnings": True})
    assert c.status_code == 200, c.text
    items = admin.get("/items").json()
    assert {i["name"] for i in items} == {"Black Label 180ml", "Red Label 750ml"}
    assert all(i["pending"] and not i["track_stock"] and i["uom_hint"] == "Nos" for i in items)
    assert admin.get("/inventory/movements").json() == [] and admin.get("/inventory/stock").json() == []


def test_27_28_baseline_unknown_and_dish(admin):
    chk = admin.post("/items", {"name": "Royal Stag 180ml", "track_stock": True, "base_unit": "Nos"}).json()
    dish = admin.post("/items", {"name": "Chicken Lollipop", "kind": "prepared_dish", "track_stock": True}).json()
    st = admin.get("/inventory/stock").json()
    rs = [s for s in st if s["item_id"] == chk["id"]][0]
    assert rs["baseline_status"] == "unknown" and rs["estimated_stock"] is None and "unknown" in rs["label"].lower()
    # sale import: product deducts, prepared dish does not
    rows = [("Royal Stag 180ml", 4, 1120), ("Chicken Lollipop", 2, 460)]
    b = upload(admin, "item_sales", csv_bytes(rows), "2026-10-01").json()
    assert all(x["match_status"] == "mapped" for x in b["rows"] if x["row_type"] == "item")
    assert admin.post(f"/imports/{b['id']}/confirm", {"acknowledge_warnings": True}).status_code == 200
    mv = admin.get("/inventory/movements").json()
    assert len(mv) == 1 and mv[0]["item"] == "Royal Stag 180ml" and D(mv[0]["quantity"]) == -4
    rs = [s for s in admin.get("/inventory/stock").json() if s["item_id"] == chk["id"]][0]
    assert D(rs["net_movement_since_baseline"]) == -4 and rs["estimated_stock"] is None  # still no authoritative balance
    # owner enters a verified opening count -> estimate appears
    assert admin.post("/inventory/opening-counts", {"item_id": chk["id"], "quantity": "24", "date": "2026-09-30"}).status_code == 200
    rs = [s for s in admin.get("/inventory/stock").json() if s["item_id"] == chk["id"]][0]
    assert D(rs["estimated_stock"]) == 20 and rs["baseline_status"] == "set"
    # reversal restores it, history kept
    assert admin.post(f"/imports/{b['id']}/reverse", {"reason": "wrong day"}).status_code == 200
    rs = [s for s in admin.get("/inventory/stock").json() if s["item_id"] == chk["id"]][0]
    assert D(rs["estimated_stock"]) == 24
    assert D(admin.get("/reports/item-sales-summary").json()["totals"]["amount"]) == 0


def test_29_purchase_stock_in_with_confirmed_conversion(admin):
    v = admin.post("/vendors", {"name": "Wine Shop"}).json()
    it = admin.post("/items", {"name": "Kingfisher 650ml", "track_stock": True, "base_unit": "Nos"}).json()
    free = admin.post("/items", {"name": "Napkins", "track_stock": False, "base_unit": "Nos"}).json()
    base = {"vendor_id": v["id"], "invoice_no": "INV-1", "invoice_date": "2026-10-01"}
    # a case differs from base unit: factor must be confirmed by the user, never guessed
    r = admin.post("/purchases", {**base, "lines": [{"item_id": it["id"], "quantity": "2", "unit": "case", "unit_price": "1000"}]})
    assert r.status_code == 422 and "conversion" in r.text
    assert admin.get("/purchases").json() == []
    r = admin.post("/purchases", {**base, "lines": [{"item_id": it["id"], "quantity": "2", "unit": "case", "conversion_factor": "12", "unit_price": "1000"},
                                                     {"item_id": free["id"], "quantity": "5", "unit": "Nos", "unit_price": "10"}],
                                  "payments": [{"amount": "500", "method": "cash", "funded_by": "account", "account_id": 1}]})
    assert r.status_code == 200, r.text
    p = r.json()
    assert D(p["total"]) == 2050 and D(p["due"]) == 1550 and p["payment_status"] == "partial"
    mv = admin.get("/inventory/movements").json()
    assert len(mv) == 1 and D(mv[0]["quantity"]) == 24 and mv[0]["movement_type"] == "purchase_in"
    # payment is not a second expense: exactly one linked expense exists
    assert len([e for e in admin.get("/expenses").json() if e["category"] == "Purchases"]) == 1


def test_31_staff_permissions(admin, staff):
    b, c = confirm_sales(admin)
    assert staff.post(f"/imports/{b['id']}/reverse", {"reason": "x"}).status_code == 403
    assert staff.get("/users").status_code == 403
    assert staff.post("/users", {"username": "zzz", "password": "password123"}).status_code == 403
    assert staff.put("/settings", {"restaurant_name": "x"}).status_code == 403
    assert staff.post("/inventory/opening-counts", {"item_id": 1, "quantity": "1"}).status_code == 403
    assert staff.get("/backups").status_code == 403


def test_auth_required_and_upload_limits(client, admin):
    assert client.get("/api/v1/customers").status_code == 401
    assert client.get("/api/v1/customers", headers={"Authorization": "Bearer junk"}).status_code == 401
    r = admin.c.post("/api/v1/attachments", headers=admin.h, files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 422
    r = admin.c.post("/api/v1/attachments", headers=admin.h, files={"file": ("../../x.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 200 and ".." not in r.json()["attachment"]
    assert admin.get("/attachments/../../etc/passwd").status_code in (404, 422)
    assert client.post("/api/v1/auth/bootstrap", json={"username": "x2", "password": "password123"}).status_code == 403


def test_32_audit_history(admin, accts):
    from test_udhari import mk_bill, mk_customer
    cid = mk_customer(admin)
    mk_bill(admin, cid, "AUD", "100")
    log = admin.get("/audit").json()
    assert {"customer", "sale_bill"} <= {a["entity_type"] for a in log}
    assert all(a["user"] == "owner" and a["ts"] for a in log)


def test_33_csv_matches_screen(admin, accts):
    from test_expenses_cash import mk_expense, pay
    e = mk_expense(admin, "1000")
    pay(admin, e["id"], "400", acct=accts["Cash Drawer"])
    mk_expense(admin, "250", category="Salary")
    screen = admin.get("/reports/expense-summary").json()
    csv_txt = admin.get("/reports/expense-summary?format=csv").text
    rows = list(csv.reader(io.StringIO(csv_txt.lstrip("﻿"))))
    assert rows[0] == screen["columns"]
    body = {r[0]: r for r in rows[1:] if r and not r[0].startswith("TOTAL")}
    for r in screen["rows"]:
        assert D(body[r["category"]][1]) == D(r["incurred"]) and D(body[r["category"]][3]) == D(r["unpaid"])
    tot = [r for r in rows if r and r[0] == "TOTAL incurred"][0]
    assert D(tot[1]) == D(screen["totals"]["incurred"]) == 1250


def test_34_backup_and_restore(admin, tmp_path):
    from app import backup
    from app.config import get_settings
    import sqlite3
    admin.post("/customers", {"name": "Backup Test", "phone": "1"})
    admin.c.post("/api/v1/attachments", headers=admin.h, files={"file": ("a.pdf", b"%PDF-1.4 hello", "application/pdf")})
    r = admin.post("/backups")
    assert r.status_code == 200 and r.json()["verified"] and r.json()["size"] > 0 and r.json()["attachments"] >= 1
    name = r.json()["name"]
    assert any(b["name"] == name for b in admin.get("/backups").json())
    if r.json()["db_kind"] != "sqlite":
        import zipfile
        with zipfile.ZipFile(get_settings().backups_dir / name) as z:
            assert b"CREATE TABLE" in z.read("database.sql") and b"Backup Test" in z.read("database.sql")
        return
    target_db, target_att = tmp_path / "restored" / "restaurant.db", tmp_path / "restored" / "attachments"
    backup.restore_backup(get_settings().backups_dir / name, target_db, target_att)
    con = sqlite3.connect(target_db)
    assert con.execute("select name from customers").fetchall() == [("Backup Test",)]
    assert any(target_att.iterdir())
    with pytest.raises(FileExistsError):
        backup.restore_backup(get_settings().backups_dir / name, target_db, target_att)


def test_migrations_run_on_fresh_database(tmp_path):
    import subprocess, sys, sqlite3, os
    dbp = tmp_path / "m.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{dbp.as_posix()}"}
    backend = os.path.dirname(os.path.dirname(__file__))
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    tables = {t[0] for t in sqlite3.connect(dbp).execute("select name from sqlite_master where type='table'")}
    assert {"customers", "receipts", "receipt_allocations", "cash_movements", "import_batches", "alembic_version"} <= tables


def test_bulk_create_then_confirm(admin):
    b = upload(admin, "item_sales", csv_bytes(SALES_ROWS), "2026-09-30").json()
    r = admin.post(f"/imports/{b['id']}/bulk", {"action": "create_new"})
    assert r.status_code == 200 and r.json()["updated"] == 3 and r.json()["summary"]["unresolved"] == 0
    assert admin.post(f"/imports/{b['id']}/bulk", {"action": "bogus"}).status_code == 422
    assert admin.post(f"/imports/{b['id']}/confirm", {"acknowledge_warnings": True}).status_code == 200
    assert {i["name"] for i in admin.get("/items").json()} == {"Imperial Blue 180ml", "Dsp Black 180ml"}
