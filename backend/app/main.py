import logging
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from .config import ROOT, get_settings
from .core import DEFAULT_SETTINGS
from .db import SessionLocal
from .models import Account, AppSetting
from .routers import auth, money, reporting, stock, udhari

log = logging.getLogger("restaurant")

# Money is serialized as exact decimal strings, never binary floats.
ENCODERS_BY_TYPE[Decimal] = lambda d: format(d, "f")


def init_defaults(db):
    """Structural configuration only (NOT demo data): default accounts + settings."""
    if db.query(Account).count() == 0:
        db.add_all([
            Account(name="Cash Drawer", type="cash", is_physical_cash=True),
            Account(name="Bank Account", type="bank"),
            Account(name="UPI", type="upi"),
            Account(name="Card Settlement", type="card"),
        ])
    for k, v in DEFAULT_SETTINGS.items():
        if db.get(AppSetting, k) is None:
            db.add(AppSetting(key=k, value=v))
    db.commit()


@asynccontextmanager
async def lifespan(_app):
    try:
        from .db import Base, unpooled_engine
        # Auto-create tables if running on fresh database (e.g. Neon PostgreSQL) using direct connection
        Base.metadata.create_all(bind=unpooled_engine)
        with SessionLocal() as db:
            init_defaults(db)
    except Exception as ex:
        log.error("Startup database initialization failed: %s", ex)
    yield


app = FastAPI(title="Restaurant Operations Manager", version="1.0.0", lifespan=lifespan)
s = get_settings()
origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins if origins else ["*"],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


API = "/api/v1"
for r in (auth, udhari, money, stock, reporting):
    app.include_router(r.router, prefix=API)
    app.include_router(r.router, prefix="/v1")


@app.get(f"{API}/health")
@app.get("/v1/health")
@app.get("/api/health")
@app.get("/health")
def health():
    from sqlalchemy import text
    with SessionLocal() as db:
        if db.bind.dialect.name == "postgresql":
            res = db.execute(text("SELECT current_database(), current_user, version()")).fetchone()
            dbname = res[0] if res else "connected"
        else:
            db.execute(text("SELECT 1"))
            dbname = "connected"
    cfg = get_settings()
    return {
        "status": "ok",
        "database": dbname,
        "neon_branch": cfg.neon_branch or "production",
        "neon_auth": bool(cfg.neon_auth_base_url),
        "auth_base_url": cfg.neon_auth_base_url or None,
    }



@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    msgs = []
    for e in exc.errors():
        loc = ".".join(str(x) for x in e["loc"] if x != "body")
        msgs.append(f"{loc}: {e['msg']}")
    return JSONResponse(status_code=422, content={"detail": "; ".join(msgs)})


@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError):
    log.warning("integrity error: %s", exc.orig)
    return JSONResponse(status_code=409, content={"detail": "This record conflicts with existing data (duplicate or in use)."})


# Serve the built frontend if present (single-process LAN deployment)
DIST = ROOT / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        f = DIST / full_path
        return FileResponse(f if f.is_file() else DIST / "index.html")
