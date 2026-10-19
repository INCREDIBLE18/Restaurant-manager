"""Optional Gemini-assisted extraction (Phase 5). Disabled unless GEMINI_ENABLED=true and GEMINI_API_KEY is set.

Safety rules enforced here:
- Only the scanned report page image is sent: never customer names/phones, ledgers or accounts.
- Bounded timeout + bounded retries; failures raise and the user falls back to local OCR/CSV/manual review.
- Output is untrusted: it must pass parsing.validate_ai_item_sales and still lands as a DRAFT needing human confirmation.
Check Google's current model names, limits and pricing before enabling; nothing here promises free usage.
NOTE: this provider has NOT been exercised against the live API in this build (no API key available).
"""
import base64
import json

import httpx

from .config import get_settings
from .parsing import ParseResult, validate_ai_item_sales

PROMPT = (
    "You are reading a scanned restaurant 'Item Sales' report. Return ONLY JSON matching: "
    '{"report_type":"item_sales","business_date":"YYYY-MM-DD or null","outlet_name":null,'
    '"rows":[{"raw_item_name":str,"category":str|null,"department":str|null,"qty_sold":"decimal string"|null,'
    '"total_amount_inr":"decimal string"|null,"row_type":"item|heading|subtotal|grand_total|unknown","page_number":int,"confidence":0..1}],'
    '"printed_grand_total_inr":null,"warnings":[]}. Include headings/subtotals/grand total as such rows; copy digits exactly; do not guess.'
)


def enabled() -> bool:
    s = get_settings()
    return bool(s.gemini_enabled and s.gemini_api_key)


def extract_item_sales(page_png_bytes: list[bytes]) -> ParseResult:
    if not enabled():
        raise RuntimeError("AI extraction is disabled")
    s = get_settings()
    parts = [{"text": PROMPT}] + [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(b).decode()}} for b in page_png_bytes]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{s.gemini_model}:generateContent"
    last = None
    for _ in range(2):  # bounded retries
        try:
            r = httpx.post(url, params={"key": s.gemini_api_key}, timeout=150,
                           json={"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0, "thinkingConfig": {"thinkingBudget": 0}}})
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return validate_ai_item_sales(json.loads(text))
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as ex:
            last = ex
    raise RuntimeError(f"AI extraction failed ({type(last).__name__}); use local OCR / CSV / manual entry instead")
