import os
import sys
import traceback
from pathlib import Path

# Add project root and backend folder to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend"))

# Flag Vercel runtime
os.environ.setdefault("VERCEL", "1")

try:
    from app.main import app
except Exception as e:
    import logging
    logging.exception("Failed to import app: %s", e)
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI()
    err_str = traceback.format_exc()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    def error_fallback(path: str):
        return JSONResponse(
            status_code=500,
            content={"error": "Backend initialization failed", "trace": err_str}
        )
