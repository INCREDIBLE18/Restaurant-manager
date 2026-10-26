"""File storage: database first (durable on serverless + included in backups), filesystem fallback for legacy files."""
import mimetypes

from fastapi.responses import Response
from sqlalchemy.orm import Session

from .config import get_settings
from .core import err
from .models import StoredFile


def save_file(db: Session, name: str, data: bytes, original_name: str = "", user_id: int | None = None) -> str:
    if not db.get(StoredFile, name):
        db.add(StoredFile(name=name, original_name=original_name[:200], size=len(data), data=data, created_by=user_id,
                          content_type=mimetypes.guess_type(name)[0] or "application/octet-stream"))
    return name


def file_response(db: Session, name: str, download_name: str | None = None) -> Response:
    f = db.get(StoredFile, name)
    if f:
        data, ctype = f.data, f.content_type
    else:
        path = get_settings().attachments_dir / name
        if not path.is_file():
            err(404, "File not found")
        data, ctype = path.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream"
    headers = {"Cache-Control": "private, max-age=3600"}
    if download_name:
        headers["Content-Disposition"] = f'attachment; filename="{download_name}"'
    return Response(content=data, media_type=ctype, headers=headers)
