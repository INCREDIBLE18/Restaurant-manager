import json
import os
import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend"))

os.environ.setdefault("VERCEL", "1")

# Ensure temporary storage exists in AWS Lambda / Vercel runtime
for sub in ["", "attachments", "backups"]:
    try:
        (Path("/tmp/data") / sub).mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

import_err = None
try:
    from backend.app.main import app as fastapi_app
except Exception as e:
    import_err = traceback.format_exc()
    fastapi_app = None


class EntryApp:
    async def __call__(self, scope, receive, send):
        if import_err is not None:
            if scope.get("type") == "http":
                body = json.dumps({"error": "Backend import failed", "trace": import_err}).encode()
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(body)).encode()]
                    ]
                })
                await send({"type": "http.response.body", "body": body})
                return
            else:
                raise RuntimeError(import_err)

        if scope.get("type") == "http":
            hdrs = dict(scope.get("headers", []))
            # If rewritten to /api, resolve the actual requested client URI
            matched = hdrs.get(b"x-matched-path", b"").decode()
            if not matched or not matched.startswith("/api/"):
                matched = hdrs.get(b"x-forwarded-uri", b"").decode()
            if matched and matched.startswith("/api/"):
                scope["path"] = matched

        try:
            await fastapi_app(scope, receive, send)
        except Exception:
            err_trace = traceback.format_exc()
            if scope.get("type") == "http":
                body = json.dumps({"error": "Request execution failed", "trace": err_trace}).encode()
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(body)).encode()]
                    ]
                })
                await send({"type": "http.response.body", "body": body})
            else:
                raise


app = EntryApp()
