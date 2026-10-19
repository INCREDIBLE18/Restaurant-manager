"""Real-document tests: local OCR on the two scanned reference PDFs. Run with: pytest -m slow"""
from pathlib import Path

import pytest

from app import parsing

REF = Path(__file__).resolve().parents[2] / "reference_pdfs"
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def item_sales():
    f = REF / "Item Sales.PDF.pdf"
    if not f.exists() or f.stat().st_size == 0 or not parsing.ocr_available():
        pytest.skip("reference PDF or OCR not available")
    return parsing.parse_item_sales(f.read_bytes(), f.name)


def test_item_sales_pdf(item_sales):
    r = item_sales
    assert r.method == "local_ocr" and r.report_date.isoformat() == "2026-09-30"
    assert r.printed_total == 26690 and r.printed_qty == 145
    items = [x for x in r.rows if x.row_type in ("item", "ditto")]
    assert any(x.name == "Chicken Lollipop" and x.qty == 1 and x.amount == 230 for x in items)
    assert not any(x.name.lower().startswith(("category:", "department:", "sub total", "grandtotal")) or x.name in ('"', "") for x in items)
    assert sum(x.amount for x in items) == 26690  # amounts reconcile with the printed grand total
    # OCR misread one quantity (Tuborg 9 -> 6); the reconciliation checks must surface it, not hide it
    assert any("mismatch" in x.notes.lower() for x in r.rows) or any("printed" in w for w in r.warnings)
    assert sum(1 for x in r.rows if x.row_type == "ditto") >= 10


def test_stock_position_pdf_names_only():
    f = REF / "Stock Position.PDF.pdf"
    if not f.exists() or f.stat().st_size == 0 or not parsing.ocr_available():
        pytest.skip("reference PDF or OCR not available")
    r = parsing.parse_stock_position(f.read_bytes(), f.name)
    assert len(r.rows) > 60
    assert all(x.qty is None and x.amount is None for x in r.rows)
    assert all(x.uom for x in r.rows)
    assert not any(x.name.lower() in ("summary", "godown", "counter") for x in r.rows)
