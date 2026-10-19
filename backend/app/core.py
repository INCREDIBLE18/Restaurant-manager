"""Shared helpers: money parsing, time, security, audit, settings."""
import base64
import hashlib
import hmac
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import bcrypt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AppSetting, AuditLog, DayClose, User

IST = ZoneInfo("Asia/Kolkata")
CENT = Decimal("0.01")
MAX_MONEY = Decimal("100000000")  # sanity ceiling: ₹10 crore per entry

DEFAULT_SETTINGS = {
    "restaurant_name": "AARAVALI, TITWALA",
    "address": "",
    "phone": "",
    "receipt_prefix": "RC",
    "bill_prefix": "UB",
    "phone_mandatory": "false",
    "variance_note_threshold": "50",
    "overdue_days": "30",
    "gemini_enabled": "false",
}


def today_ist() -> date:
    return datetime.now(IST).date()


def err(status: int, msg: str):
    raise HTTPException(status_code=status, detail=msg)


def money(value, field="amount", allow_zero=False, allow_negative=False) -> Decimal:
    """Parse to a 2-dp Decimal. Rejects floats-as-garbage, NaN, negatives, absurd values."""
    if value is None or (isinstance(value, str) and not value.strip()):
        err(422, f"{field} is required")
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        err(422, f"{field} is not a valid number")
    if not d.is_finite():
        err(422, f"{field} is not a valid number")
    d = d.quantize(CENT, rounding=ROUND_HALF_UP)
    if not allow_negative:
        if d < 0:
            err(422, f"{field} cannot be negative")
        if d == 0 and not allow_zero:
            err(422, f"{field} must be greater than zero")
    if abs(d) > MAX_MONEY:
        err(422, f"{field} is unreasonably large")
    return d


def qty(value, field="quantity", allow_zero=False) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        err(422, f"{field} is required")
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        err(422, f"{field} is not a valid number")
    if not d.is_finite() or d < 0 or (d == 0 and not allow_zero):
        err(422, f"{field} must be positive")
    if d > Decimal("10000000"):
        err(422, f"{field} is unreasonably large")
    return d.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ---------- passwords & tokens ----------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user: User) -> str:
    s = get_settings()
    payload = {"uid": user.id, "exp": int(time.time()) + s.token_ttl_hours * 3600}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(s.secret_key.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> int | None:
    s = get_settings()
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(s.secret_key.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        payload = json.loads(_unb64(body))
        if payload["exp"] < time.time():
            return None
        return int(payload["uid"])
    except Exception:
        return None


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.lower().startswith("bearer "):
        err(401, "Not authenticated")
    uid = read_token(authorization[7:])
    user = db.get(User, uid) if uid else None
    if not user or not user.active:
        err(401, "Session expired or invalid")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        err(403, "Admin permission required")
    return user


# ---------- audit ----------
def audit(db: Session, user: User | None, action: str, entity_type: str, entity_id, before=None, after=None, reason=""):
    db.add(AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "",
        action=action, entity_type=entity_type, entity_id=str(entity_id),
        before=_jsonable(before), after=_jsonable(after), reason=reason or "",
    ))


def _jsonable(v):
    if v is None:
        return None
    return json.loads(json.dumps(v, default=str))


# ---------- settings ----------
def get_setting(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    return row.value if row else DEFAULT_SETTINGS.get(key, "")


def all_settings(db: Session) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for r in db.query(AppSetting).all():
        out[r.key] = r.value
    return out


def assert_day_open(db: Session, d: date):
    """Postings into a finalized business day are blocked; correct via reversal today or admin reopen."""
    dc = db.query(DayClose).filter(DayClose.business_date == d).first()
    if dc and dc.status == "finalized":
        err(409, f"Business day {d.isoformat()} is finalized. An admin must reopen it (with a reason) before changes are posted to it.")


def norm_name(s: str) -> str:
    """Matching key: lowercase alphanumerics only, so OCR spacing/punctuation differences still match."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


METHODS = {"cash", "upi", "card", "bank", "other"}


def parse_date(v, field="date") -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except Exception:
        err(422, f"{field} must be YYYY-MM-DD")
