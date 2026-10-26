import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import (
    DEFAULT_SETTINGS, parse_date, admin_user, all_settings, audit, current_user, err, hash_password, make_token, money,
    verify_password,
)
from ..db import get_db
from ..files import file_response, save_file
from ..ledger import account_balance, batch_account_balances
from ..models import Account, AppSetting, AuditLog, User, utcnow

router = APIRouter()

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".csv", ".xlsx", ".webp"}


class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str
    password: str
    full_name: str = ""
    role: str = "staff"


def user_out(u: User):
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role, "active": u.active,
            "last_login": u.last_login.isoformat() if u.last_login else None}


def check_password_strength(pw: str):
    if len(pw) < 8:
        err(422, "Password must be at least 8 characters")


@router.get("/auth/status")
def status(db: Session = Depends(get_db)):
    s = get_settings()
    return {
        "needs_setup": db.query(User).count() == 0,
        "neon_auth": bool(s.neon_auth_base_url),
        "neon_auth_base_url": s.neon_auth_base_url or None,
    }



@router.post("/auth/bootstrap")
def bootstrap(body: UserIn, db: Session = Depends(get_db)):
    """First-run only: creates the initial admin. Refused once any user exists."""
    if db.query(User).count() > 0:
        err(403, "Setup already completed")
    check_password_strength(body.password)
    u = User(username=body.username.strip().lower(), full_name=body.full_name, role="admin",
             password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit(db, u, "bootstrap", "user", u.id)
    db.commit()
    return {"token": make_token(u), "user": user_out(u)}


_FAILS: dict[str, list] = {}  # key -> [count, locked_until]
MAX_FAILS, LOCK_SECONDS = 5, 300


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = f"{body.username.strip().lower()}|{request.client.host if request.client else ''}"
    rec = _FAILS.get(key)
    if rec and rec[1] > time.time():
        err(429, f"Too many failed attempts. Try again in {int(rec[1] - time.time()) + 1} seconds.")
    u = db.query(User).filter(User.username == body.username.strip().lower()).first()
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        rec = _FAILS.setdefault(key, [0, 0])
        rec[0] += 1
        if rec[0] >= MAX_FAILS:
            rec[0], rec[1] = 0, time.time() + LOCK_SECONDS
        err(401, "Invalid username or password")
    _FAILS.pop(key, None)
    u.last_login = utcnow()
    db.commit()
    return {"token": make_token(u), "user": user_out(u)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.post("/auth/change-password")
def change_password(body: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.get("old_password", ""), user.password_hash):
        err(403, "Current password is wrong")
    check_password_strength(body.get("new_password", ""))
    user.password_hash = hash_password(body["new_password"])
    audit(db, user, "change_password", "user", user.id)
    db.commit()
    return {"ok": True}


# ---- users (admin)
@router.get("/users")
def users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [user_out(u) for u in db.query(User).order_by(User.id)]


@router.post("/users")
def add_user(body: UserIn, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if body.role not in ("admin", "staff"):
        err(422, "role must be admin or staff")
    check_password_strength(body.password)
    name = body.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,40}", name):
        err(422, "Username must be 3-40 characters (letters, digits, . _ -)")
    if db.query(User).filter(User.username == name).first():
        err(409, "Username already exists")
    u = User(username=name, full_name=body.full_name, role=body.role, password_hash=hash_password(body.password))
    db.add(u)
    db.flush()
    audit(db, admin, "create", "user", u.id, after={"username": name, "role": body.role})
    db.commit()
    return user_out(u)


@router.patch("/users/{uid}")
def edit_user(uid: int, body: dict, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        err(404, "User not found")
    if "role" in body:
        if body["role"] not in ("admin", "staff"):
            err(422, "role must be admin or staff")
        u.role = body["role"]
    if "active" in body:
        if u.id == admin.id and not body["active"]:
            err(422, "You cannot deactivate yourself")
        u.active = bool(body["active"])
    if body.get("password"):
        check_password_strength(body["password"])
        u.password_hash = hash_password(body["password"])
    if db.query(User).filter(User.role == "admin", User.active.is_(True)).count() == 0:
        db.rollback()
        err(422, "At least one active admin is required")
    audit(db, admin, "update", "user", u.id, after={k: v for k, v in body.items() if k != "password"})
    db.commit()
    return user_out(u)


# ---- settings
@router.get("/settings")
def get_settings_api(_: User = Depends(current_user), db: Session = Depends(get_db)):
    s = all_settings(db)
    s["gemini_enabled"] = "true" if (get_settings().gemini_enabled and get_settings().gemini_api_key) else "false"
    return s


@router.put("/settings")
def put_settings(body: dict, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    for k, v in body.items():
        if k not in DEFAULT_SETTINGS:
            err(422, f"Unknown setting '{k}'")
        if k in ("variance_note_threshold", "overdue_days"):
            money(v, k, allow_zero=True)
        row = db.get(AppSetting, k)
        if row:
            row.value = str(v)
        else:
            db.add(AppSetting(key=k, value=str(v)))
    audit(db, admin, "update", "settings", "app", after=body)
    db.commit()
    return all_settings(db)


# ---- accounts
@router.get("/accounts")
def accounts(_: User = Depends(current_user), db: Session = Depends(get_db)):
    accs = db.query(Account).order_by(Account.id).all()
    bals = batch_account_balances(db, accs)
    return [{"id": a.id, "name": a.name, "type": a.type, "is_physical_cash": a.is_physical_cash, "active": a.active,
             "opening_balance": a.opening_balance, "balance": bals.get(a.id, a.opening_balance)}
            for a in accs]


@router.post("/accounts")
def add_account(body: dict, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    name = (body.get("name") or "").strip()
    typ = body.get("type", "other")
    if not name:
        err(422, "Account name required")
    if typ not in ("cash", "bank", "upi", "card", "owner_personal", "staff_advance", "other"):
        err(422, "Invalid account type")
    if db.query(Account).filter(Account.name == name).first():
        err(409, "An account with this name exists")
    a = Account(name=name, type=typ, is_physical_cash=(typ == "cash"),
                opening_balance=money(body.get("opening_balance", 0), "opening balance", allow_zero=True, allow_negative=True))
    db.add(a)
    db.flush()
    audit(db, admin, "create", "account", a.id, after={"name": name, "type": typ})
    db.commit()
    return {"id": a.id}


@router.patch("/accounts/{aid}")
def edit_account(aid: int, body: dict, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    a = db.get(Account, aid)
    if not a:
        err(404, "Account not found")
    if "active" in body:
        a.active = bool(body["active"])
    if "name" in body and body["name"].strip():
        a.name = body["name"].strip()
    if "opening_balance" in body:
        a.opening_balance = money(body["opening_balance"], "opening balance", allow_zero=True, allow_negative=True)
        a.opening_date = parse_date(body["opening_date"]) if body.get("opening_date") else a.opening_date
    audit(db, admin, "update", "account", a.id, after=body)
    db.commit()
    return {"ok": True}


# ---- attachments
@router.post("/attachments")
async def upload(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        err(422, f"File type {ext or '(none)'} not allowed")
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        err(413, f"File larger than {get_settings().max_upload_mb} MB")
    if not data:
        err(422, "Empty file")
    name = f"{uuid.uuid4().hex}{ext}"
    save_file(db, name, data, file.filename or "", user.id)
    db.commit()
    return {"attachment": name, "filename": file.filename, "size": len(data)}


@router.get("/attachments/{name}")
def download(name: str, _: User = Depends(current_user), db: Session = Depends(get_db)):
    if not re.fullmatch(r"[0-9a-f]{32}\.[a-z0-9]{2,5}", name):
        err(404, "Not found")
    return file_response(db, name)


@router.get("/audit")
def audit_log(limit: int = 200, entity_type: str = "", _: User = Depends(admin_user), db: Session = Depends(get_db)):
    q = db.query(AuditLog).order_by(AuditLog.id.desc())
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    return [{"id": a.id, "ts": a.ts.isoformat(), "user": a.username, "action": a.action, "entity_type": a.entity_type,
             "entity_id": a.entity_id, "before": a.before, "after": a.after, "reason": a.reason}
            for a in q.limit(min(limit, 1000))]


# ---- Bill OCR
@router.post("/ocr/bill")
async def ocr_bill(file: UploadFile = File(...), _: User = Depends(current_user)):
    """Use Gemini Vision to extract structured bill data from a photo.
    Returns: bill_no, date, total, items list, notes."""
    import base64
    import json as _json

    cfg = get_settings()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        err(422, "Only image files are supported for OCR (PNG/JPG/JPEG/WEBP)")

    data = await file.read()
    if len(data) > cfg.max_upload_mb * 1024 * 1024:
        err(413, f"File larger than {cfg.max_upload_mb} MB")
    if not data:
        err(422, "Empty file")

    # Try Gemini Vision
    if not cfg.gemini_api_key:
        err(503, "OCR feature requires GEMINI_API_KEY to be configured on the server")

    b64 = base64.b64encode(data).decode()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp", "gif": "image/gif"}.get(ext.lstrip("."), "image/jpeg")

    prompt = """You are a receipt/bill parser for a restaurant POS system.
Analyze this restaurant bill image and extract the following information in JSON format.
Be precise - only include data that is clearly visible.

Return ONLY valid JSON with this exact structure:
{
  "bill_no": "string or null",
  "date": "YYYY-MM-DD or null",
  "total": "numeric string or null",
  "items": [
    {"name": "item name", "qty": 1, "rate": 0.0, "amount": 0.0}
  ],
  "notes": "any extra info like table number, restaurant name, etc or empty string"
}

Rules:
- bill_no: the bill/invoice number shown on the receipt
- date: convert any date format to YYYY-MM-DD (e.g. 12/10/26 → 2026-10-12)
- total: the final grand total amount (numeric only, no currency symbol)
- items: each line item with name, quantity, rate per unit, and total amount
- If any field is not clearly visible, use null for that field
- For items, if qty or rate is unclear but amount is there, set qty=1 and rate=amount"""

    try:
        import urllib.request
        payload = _json.dumps({
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime, "data": b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
        }).encode()

        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.gemini_model}:generateContent?key={cfg.gemini_api_key}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = _json.loads(resp.read())

        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Strip markdown code blocks if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        parsed = _json.loads(text)
        return {"ok": True, "data": parsed}
    except Exception as ex:
        return {"ok": False, "error": str(ex), "data": {
            "bill_no": None, "date": None, "total": None, "items": [], "notes": ""
        }}

