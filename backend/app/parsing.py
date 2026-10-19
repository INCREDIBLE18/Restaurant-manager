"""PDF/image/CSV extraction for the Item Sales and Stock Position reports.

Order: native PDF text -> local OCR (RapidOCR / ONNX, no cloud) -> (optional, off by default) Gemini.
Everything produced here is an UNTRUSTED SUGGESTION that must pass a human review screen.

Stock Position: ONLY item name + UOM label are ever extracted. Quantity/value columns are never read.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
DITTO_TOKENS = {'"', "''", "'", "”", "“", "„", ",,", "``", "ʺ", "″", "11", "i", "l", "ii", "1", "|", "!!", "!", "¨", "..", "”“"}
MAX_QTY = Decimal("100000")
MAX_AMOUNT = Decimal("10000000")


@dataclass
class RawLine:
    page: int
    name: str
    nums: dict = field(default_factory=dict)  # column -> raw text
    conf: float = 1.0


@dataclass
class ParsedRow:
    seq: int
    page: int
    row_type: str  # item|ditto|heading|subtotal|grand_total|end|unknown
    raw_name: str
    name: str = ""
    category: str = ""
    department: str = ""
    qty: Decimal | None = None
    amount: Decimal | None = None
    cancel_orders: Decimal | None = None
    uom: str = ""
    confidence: float = 1.0
    notes: str = ""
    needs_review: bool = False
    exclude_reason: str = ""


@dataclass
class ParseResult:
    report_type: str
    method: str
    report_date: date | None = None
    print_info: str = ""
    outlet: str = ""
    rows: list = field(default_factory=list)
    printed_total: Decimal | None = None
    printed_qty: Decimal | None = None
    warnings: list = field(default_factory=list)


def dec(s) -> Decimal | None:
    if s is None:
        return None
    t = str(s).replace(",", "").replace(" ", "").strip()
    if t in ("", "-"):
        return None
    t = t.replace("O", "0").replace("o", "0") if re.fullmatch(r"[\dOo.,]+", t) else t
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def respace(name: str) -> tuple[str, bool]:
    """OCR often drops spaces. Rebuild plausible spacing; return (name, changed)."""
    if " " in name.strip() and not re.search(r"[a-z][A-Z]", name):
        return name.strip(), False
    s = name.strip()
    t = re.sub(r"^([A-Z])(?=[A-Z][a-z])", lambda m: m.group(1) + " ", s)
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
    t = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", t)
    t = re.sub(r"(?<=\d)(?=[A-Za-z])(?!(?:ml|l|ltr|lte|g|kg|mg)\b)", " ", t)
    t = re.sub(r"(?<=[a-z])(?=\d)", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t, t != s


def parse_report_date(text: str):
    m = re.search(r"(\d{1,2})\s*-\s*([A-Za-z]{3})[a-z]*\s*-\s*(\d{4})", text)
    if m and m.group(2).lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------- OCR backend
_ocr = None


def ocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        import pypdfium2  # noqa: F401
        return True
    except Exception:
        return False


def _get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def _render_pages(data: bytes, filename: str):
    import numpy as np
    from PIL import Image
    if filename.lower().endswith((".png", ".jpg", ".jpeg")):
        yield Image.open(io.BytesIO(data)).convert("RGB")
        return
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    for i in range(len(pdf)):
        yield pdf[i].render(scale=2.5).to_pil().convert("RGB")


def render_png_pages(data: bytes, filename: str, scale: float = 2.0) -> list[bytes]:
    """Page images only (what the optional AI provider receives; never any ledger data)."""
    out = []
    for img in _render_pages(data, filename):
        buf = io.BytesIO()
        img.convert("L").save(buf, format="JPEG", quality=80)
        out.append(buf.getvalue())
    return out


def ocr_pages(data: bytes, filename: str):
    """-> list of pages; each page = (width, [(xc, yc, x1, x2, text, score)])"""
    import numpy as np
    eng = _get_ocr()
    pages = []
    for img in _render_pages(data, filename):
        res, _ = eng(np.array(img))
        boxes = []
        for box, text, score in (res or []):
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            boxes.append(((min(xs) + max(xs)) / 2, sum(ys) / 4, min(xs), max(xs), text.strip(), float(score)))
        pages.append((img.width, boxes))
    return pages


def group_lines(boxes, tol=24):
    lines = []
    for b in sorted(boxes, key=lambda b: b[1]):
        if lines and abs(lines[-1]["y"] - b[1]) < tol:
            ln = lines[-1]
            ln["boxes"].append(b)
            ln["y"] = sum(x[1] for x in ln["boxes"]) / len(ln["boxes"])
        else:
            lines.append({"y": b[1], "boxes": [b]})
    for ln in lines:
        ln["boxes"].sort(key=lambda b: b[2])
    return lines


HEADER_KEYS = ["qty", "total", "cancel", "no", "free", "void", "compl", "guest", "staff", "stock"]
JUNK = re.compile(r"^(page\s*\d+\s*of\s*\d+|scanned\s*with.*|.*oken.*scanner)$", re.I)


def _columns(width, lines):
    """x-centres of numeric columns from the header; falls back to the sample layout."""
    centers = {}
    for ln in lines[:8]:
        texts = [b[4].lower().replace(" ", "") for b in ln["boxes"]]
        if "qty" in texts or "cancel" in texts or "total" in texts:
            for b in ln["boxes"]:
                t = b[4].lower().replace(" ", "")
                if t in HEADER_KEYS and t not in centers:
                    centers[t] = b[0]
    if "qty" in centers and "total" in centers:
        return centers, True
    return {"qty": 0.4135 * width, "total": 0.470 * width, "cancel": 0.534 * width, "no": 0.60 * width}, False


def _col_of(x, centers):
    names = sorted(centers, key=lambda k: centers[k])
    xs = [centers[k] for k in names]
    first_num_left = (xs[0] - (xs[1] - xs[0]) * 0.55) if len(xs) > 1 else xs[0] - 60
    if x < first_num_left:
        return "name"
    best = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
    # numbers are right-aligned: bias toward the column whose centre is to the left of the value
    return names[best]


def item_sales_lines_from_ocr(pages):
    out, meta = [], {"text": []}
    for pno, (width, boxes) in enumerate(pages, start=1):
        boxes = [b for b in boxes if not JUNK.match(b[4].replace("  ", " "))]
        lines = group_lines(boxes)
        centers, found = _columns(width, lines)
        hdr_idx = -1
        for i, ln in enumerate(lines[:10]):
            if any(b[4].lower().replace(" ", "") in ("itemname", "qty", "total") for b in ln["boxes"]):
                hdr_idx = max(hdr_idx, i)
        first_hdr = next((i for i, ln in enumerate(lines[:10]) if any(
            b[4].lower().replace(" ", "") == "itemname" for b in ln["boxes"])), None)
        if pno == 1 and first_hdr is not None:
            meta["text"] = [" ".join(b[4] for b in ln["boxes"]) for ln in lines[:first_hdr]]
        # header may span two lines ("Qty / sold"); skip any following line made only of header words
        while hdr_idx + 1 < len(lines) and all(
                re.fullmatch(r"(sold|amount|orders|charge|charae|items|bills|qty|qtv|pios|item|name)", b[4].lower().replace(" ", ""))
                for b in lines[hdr_idx + 1]["boxes"]):
            hdr_idx += 1
        for i, ln in enumerate(lines):
            if i <= hdr_idx:
                continue
            whole = re.sub(r"\s+", "", " ".join(b[4] for b in ln["boxes"])).lower()
            if "endofreport" in whole:
                out.append(RawLine(pno, "End Of Report", {}))
                continue
            name_parts, nums, conf = [], {}, []
            for b in ln["boxes"]:
                col = _col_of(b[0], centers)
                if col == "name":
                    name_parts.append(b[4])
                else:
                    nums.setdefault(col, b[4])
                conf.append(b[5])
            if not name_parts and not any(dec(v) is not None for v in nums.values()):
                continue
            out.append(RawLine(pno, " ".join(name_parts), nums, min(conf) if conf else 1.0))
    return out, meta


# --------------------------------------------------------------------------- text-layer / CSV backends
NUM = r"-?[\d,]+(?:\.\d+)?"


def item_sales_lines_from_text(text: str):
    out, head = [], []
    page = 1
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln:
            continue
        if re.match(r"(?i)^page\s*\d+\s*of\s*\d+", ln):
            page += 1
            continue
        m = re.match(rf"^(.*?)\s+({NUM})\s+({NUM})(?:\s+({NUM}))?\s*$", ln)
        if m and not re.match(r"(?i)^(date|print)", ln):
            nums = {"qty": m.group(2), "total": m.group(3)}
            if m.group(4):
                nums["cancel"] = m.group(4)
            out.append(RawLine(page, m.group(1).strip(), nums))
        elif re.search(r"(?i)end of report", ln):
            out.append(RawLine(page, ln, {}))
        elif len(out) == 0:
            head.append(ln)
        else:
            out.append(RawLine(page, ln, {}))
    return out, {"text": head}


def item_sales_lines_from_csv(text: str):
    rdr = csv.reader(io.StringIO(text))
    rows = list(rdr)
    out = []
    if not rows:
        return out, {"text": []}
    hdr = [c.strip().lower() for c in rows[0]]

    def col(*names):
        for n in names:
            for i, h in enumerate(hdr):
                if n in h:
                    return i
        return None
    ni, qi, ai = col("item", "name"), col("qty", "quantity"), col("amount", "total")
    if None in (ni, qi, ai):
        raise ValueError("CSV needs columns for item name, qty and amount")
    for r in rows[1:]:
        if len(r) <= max(ni, qi, ai):
            continue
        out.append(RawLine(1, r[ni].strip(), {"qty": r[qi], "total": r[ai]}))
    return out, {"text": []}


# --------------------------------------------------------------------------- classification (the core rules)
def classify_item_sales(lines, meta_text, method) -> ParseResult:
    res = ParseResult("item_sales", method)
    head = " ".join(meta_text.get("text", []))
    res.report_date = parse_report_date(head)
    mp = re.search(r"Print\s*Date[:\s]*([^\n]+)", head, re.I)
    res.print_info = mp.group(1).strip() if mp else ""
    if meta_text.get("text"):
        res.outlet = meta_text["text"][0].strip()
    dept = cat = ""
    prev_item = None  # last item-like row since last structural row
    seq = 0
    group_rows = []  # rows since last subtotal (for subtotal check)
    cat_rows, dept_rows = [], []
    cat_row = dept_row = None
    for ln in lines:
        seq += 1
        raw = ln.name.strip()
        flat = re.sub(r"\s+", "", raw).lower()
        qty = dec(ln.nums.get("qty"))
        amt = dec(ln.nums.get("total"))
        canc = dec(ln.nums.get("cancel"))
        r = ParsedRow(seq=seq, page=ln.page, row_type="unknown", raw_name=raw, qty=qty, amount=amt,
                      cancel_orders=canc, confidence=ln.conf, department=dept, category=cat)
        if "endofreport" in flat or flat.startswith("xxx"):
            r.row_type, r.exclude_reason = "end", "End of report marker"
        elif flat.startswith("grandtotal"):
            r.row_type, r.exclude_reason = "grand_total", "Grand total (used for reconciliation only)"
            res.printed_total, res.printed_qty = amt, qty
        elif flat.startswith("subtotal"):
            r.row_type, r.exclude_reason = "subtotal", "Sub total row (not a product)"
            prev_item = None
            r.notes = ""
            group = [x for x in group_rows if x.row_type in ("item", "ditto")]
            if group and qty is not None and amt is not None:
                sq, sa = sum((x.qty or 0) for x in group), sum((x.amount or 0) for x in group)
                if sq != qty or sa != amt:
                    r.needs_review = True
                    r.notes = f"Sub total mismatch: printed {qty}/{amt}, rows add to {sq}/{sa} — check OCR of the rows above."
                    for x in group:
                        x.needs_review = True
                        x.notes = (x.notes + " " if x.notes else "") + "Within a sub-total group that does not reconcile."
            group_rows = []
        elif flat.startswith("department:") or flat.startswith("dept:"):
            r.row_type, r.exclude_reason = "heading", "Department heading (not a product)"
            dept = raw.split(":", 1)[1].strip()
            r.department, cat = dept, ""
            _close_group(res, cat_row, cat_rows, "Category")
            _close_group(res, dept_row, dept_rows, "Department")
            dept_row, cat_row, cat_rows, dept_rows = r, None, [], []
            prev_item, group_rows = None, []
        elif flat.startswith("category:"):
            r.row_type, r.exclude_reason = "heading", "Category heading (not a product)"
            cat = raw.split(":", 1)[1].strip()
            r.category = cat
            _close_group(res, cat_row, cat_rows, "Category")
            cat_row, cat_rows = r, []
            prev_item, group_rows = None, []
        elif (qty is not None or amt is not None) and (not flat or flat in DITTO_TOKENS or re.fullmatch(r"[^a-z0-9]{1,3}", flat)):
            # ditto mark / missing name: same product at a different price, structure-dependent
            r.row_type = "ditto"
            if prev_item is not None:
                r.name, r.notes = prev_item.name, f"Ditto mark — inherited '{prev_item.name}' from the row above."
                r.confidence = min(r.confidence, 0.9)
            else:
                r.needs_review, r.notes = True, "Ditto mark with no clear item above — choose the item or exclude."
        elif qty is not None and amt is not None and flat:
            r.row_type = "item"
            name, changed = respace(raw)
            r.name = name
            if changed:
                r.notes = "OCR dropped spaces; name was re-spaced automatically."
            prev_item = r
            group_rows = []
        else:
            r.row_type, r.needs_review = "unknown", True
            r.notes = "Could not read quantity/amount for this line."
            r.exclude_reason = "Unreadable row — review"
        for lim, v, nm in ((MAX_QTY, qty, "quantity"), (MAX_AMOUNT, amt, "amount")):
            if v is not None and (v < 0 or v > lim):
                r.needs_review, r.notes = True, (r.notes + f" Implausible {nm} {v}.").strip()
        if r.row_type in ("item", "ditto"):
            if qty is None or amt is None:
                r.needs_review, r.notes = True, (r.notes + " Missing quantity or amount.").strip()
            group_rows.append(r)
            cat_rows.append(r)
            dept_rows.append(r)
        res.rows.append(r)
    _close_group(res, cat_row, cat_rows, "Category")
    _close_group(res, dept_row, dept_rows, "Department")
    items = [x for x in res.rows if x.row_type in ("item", "ditto")]
    if not res.report_date:
        res.warnings.append("Report date could not be read; enter it manually.")
    if not any(x.row_type == "grand_total" for x in res.rows):
        res.warnings.append("Printed grand total not detected; reconciliation check unavailable.")
    if not items:
        res.warnings.append("No item rows were extracted.")
    return res


def _close_group(res, head_row, rows, label):
    """Compare a Category/Department heading's printed totals with the item rows beneath it."""
    if head_row is None or head_row.qty is None or head_row.amount is None:
        return
    items = [x for x in rows if x.row_type in ("item", "ditto")]
    sq, sa = sum((x.qty or 0) for x in items), sum((x.amount or 0) for x in items)
    if sq != head_row.qty or sa != head_row.amount:
        msg = f"{label} '{head_row.raw_name}': printed {head_row.qty}/{head_row.amount} but rows add to {sq}/{sa}."
        res.warnings.append(msg)
        head_row.needs_review = True
        head_row.notes = msg
        if label == "Category":  # department-level totals are too coarse to blame individual rows
            for x in items:
                x.needs_review = True


def parse_item_sales(data: bytes, filename: str) -> ParseResult:
    fn = filename.lower()
    if fn.endswith(".csv"):
        lines, meta = item_sales_lines_from_csv(data.decode("utf-8-sig", errors="replace"))
        return classify_item_sales(lines, meta, "csv")
    if fn.endswith(".pdf"):
        text = ""
        try:
            import pypdf
            r = pypdf.PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in r.pages)
        except Exception:
            text = ""
        if len(re.findall(r"\d", text)) > 40 and re.search(r"(?i)item", text):
            lines, meta = item_sales_lines_from_text(text)
            return classify_item_sales(lines, meta, "pdf_text")
    if not ocr_available():
        raise RuntimeError("No text layer found and local OCR is not installed (pip install rapidocr-onnxruntime). "
                           "Upload a CSV instead or install the OCR dependency.")
    pages = ocr_pages(data, filename)
    lines, meta = item_sales_lines_from_ocr(pages)
    return classify_item_sales(lines, meta, "local_ocr")


# --------------------------------------------------------------------------- Stock Position: NAMES + UOM ONLY
UOM_RE = re.compile(r"^(nos|no|kg|kgs|gm|g|ltr|lt|l|pcs|pc|ml|box|btl|bottle|pkt|case|unit|units)$", re.I)


def parse_stock_position(data: bytes, filename: str) -> ParseResult:
    """Extract candidate catalogue names + UOM labels. Quantity/value columns are deliberately never read."""
    res = ParseResult("stock_position", "local_ocr")
    if filename.lower().endswith(".csv"):
        res.method = "csv"
        rdr = list(csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))
        hdr = [c.strip().lower() for c in rdr[0]] if rdr else []
        ni = next((i for i, h in enumerate(hdr) if "item" in h or "name" in h), 0)
        ui = next((i for i, h in enumerate(hdr) if "uom" in h or "unit" in h), None)
        for i, r in enumerate(rdr[1:], start=1):
            if len(r) > ni and r[ni].strip():
                res.rows.append(ParsedRow(seq=i, page=1, row_type="item", raw_name=r[ni].strip(), name=r[ni].strip(),
                                          uom=(r[ui].strip() if ui is not None and len(r) > ui else "")))
        return res
    if not ocr_available():
        raise RuntimeError("Local OCR is not installed (pip install rapidocr-onnxruntime); upload a CSV of item names instead.")
    pages = ocr_pages(data, filename)
    seen, seq = set(), 0
    in_summary = False
    from .core import norm_name
    for pno, (width, boxes) in enumerate(pages, start=1):
        boxes = [b for b in boxes if not JUNK.match(b[4])]
        lines = group_lines(boxes)
        uom_x = None
        for ln in lines[:8]:
            for b in ln["boxes"]:
                if b[4].lower().strip() == "uom":
                    uom_x = b[2]
        if uom_x is None:
            uom_x = 0.30 * width
        for ln in lines:
            name_parts, uom = [], ""
            for b in ln["boxes"]:
                if b[0] < uom_x - 5:
                    name_parts.append(b[4])
                elif b[0] < uom_x + 0.07 * width and UOM_RE.match(b[4].strip()):
                    uom = b[4].strip()
                # every other box (Open, Purchase, Issued, Closing, values …) is intentionally ignored
            name = " ".join(name_parts).strip()
            if re.fullmatch(r"(?i)summary", name):
                in_summary = True
            if in_summary or not uom or not name:
                continue  # 'Summary' section only repeats names already listed
            low = re.sub(r"\s+", "", name).lower()
            if low in ("itemname", "godown", "counter") or low.startswith("dept:"):
                continue
            name, changed = respace(name)
            key = norm_name(name)
            if key in seen:
                continue
            seen.add(key)
            seq += 1
            res.rows.append(ParsedRow(seq=seq, page=pno, row_type="item", raw_name=name, name=name, uom=uom,
                                      notes="OCR dropped spaces; re-spaced automatically." if changed else ""))
    res.warnings.append("Quantities, values, Open/Purchase/Issued/Closing columns were NOT read and are ignored by design.")
    return res


# --------------------------------------------------------------------------- AI payload validation (optional provider)
def validate_ai_item_sales(payload) -> ParseResult:
    """Strict validation of model JSON. Raises ValueError on anything malformed; result is still only a draft."""
    if not isinstance(payload, dict) or payload.get("report_type") != "item_sales" or not isinstance(payload.get("rows"), list):
        raise ValueError("AI output is not a valid item_sales document")
    lines, text = [], {"text": []}
    for i, r in enumerate(payload["rows"]):
        if not isinstance(r, dict) or not isinstance(r.get("raw_item_name"), str):
            raise ValueError(f"row {i}: raw_item_name missing")
        for k in ("qty_sold", "total_amount_inr"):
            v = r.get(k)
            if v is not None and (not isinstance(v, str) or dec(v) is None):
                raise ValueError(f"row {i}: {k} must be a decimal string")
        rt = r.get("row_type", "unknown")
        if rt not in ("item", "heading", "subtotal", "grand_total", "unknown"):
            raise ValueError(f"row {i}: invalid row_type")
        name = r["raw_item_name"]
        if rt == "heading":
            name = f"Category: {name}"
        elif rt == "subtotal":
            name = "Sub Total"
        elif rt == "grand_total":
            name = "GrandTotal"
        lines.append(RawLine(int(r.get("page_number") or 1), name,
                             {"qty": r.get("qty_sold"), "total": r.get("total_amount_inr")}, float(r.get("confidence") or 0.5)))
    bd = payload.get("business_date")
    res = classify_item_sales(lines, text, "ai")
    if bd:
        try:
            res.report_date = date.fromisoformat(bd)
        except ValueError:
            raise ValueError("business_date invalid")
    for x in res.rows:
        x.needs_review = True  # AI output is always flagged for review
    res.warnings.append("Extracted by AI — every row requires human review.")
    return res
