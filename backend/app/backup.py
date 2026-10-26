"""Backup = zip(database snapshot + attachments + manifest). A backup is only reported successful
after the zip was written, is non-empty, passes zipfile integrity test and contains the database."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.engine import make_url

from .config import get_settings


def _sqlite_path(url: str) -> Path | None:
    u = make_url(url)
    return Path(u.database) if u.drivername.startswith("sqlite") and u.database else None


def create_backup(database_url: str | None = None, attachments_dir: Path | None = None, out_dir: Path | None = None) -> dict:
    s = get_settings()
    url = database_url or s.database_url
    att = attachments_dir or s.attachments_dir
    out = out_dir or s.backups_dir
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"backup-{stamp}.zip"
    target = out / name
    with tempfile.TemporaryDirectory() as tmp:
        tmpdb = None
        src = _sqlite_path(url)
        if src is not None:
            if not src.exists():
                raise HTTPException(500, "Database file not found; backup aborted")
            tmpdb = Path(tmp) / "database.sqlite"
            a, b = sqlite3.connect(str(src)), sqlite3.connect(str(tmpdb))
            try:
                a.backup(b)  # consistent snapshot even while the app is writing
            finally:
                b.close()
                a.close()
            db_member, kind = "database.sqlite", "sqlite"
        else:
            exe = shutil.which("pg_dump") or next(iter(sorted(Path("C:/Program Files/PostgreSQL").glob("*/bin/pg_dump.exe"), reverse=True)), None)
            exe = str(exe) if exe else None
            if not exe:
                raise HTTPException(500, "pg_dump not found on PATH; cannot back up PostgreSQL")
            u = make_url(url)
            tmpdb = Path(tmp) / "database.sql"
            env = {**os.environ, "PGPASSWORD": u.password or ""}
            r = subprocess.run([exe, "-h", u.host or "localhost", "-p", str(u.port or 5432), "-U", u.username or "postgres",
                                "-f", str(tmpdb), u.database], env=env, capture_output=True, text=True)
            if r.returncode != 0:
                raise HTTPException(500, f"pg_dump failed: {r.stderr[:300]}")
            db_member, kind = "database.sql", "postgres"
        files = [p for p in att.rglob("*") if p.is_file()] if att.exists() else []
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(tmpdb, db_member)
            for f in files:
                z.write(f, f"attachments/{f.relative_to(att).as_posix()}")
            z.writestr("manifest.json", json.dumps({"created": stamp, "db_kind": kind, "db_member": db_member,
                                                    "attachment_count": len(files)}))
    # verify before claiming success
    if not target.exists() or target.stat().st_size == 0:
        raise HTTPException(500, "Backup file was not written")
    with zipfile.ZipFile(target) as z:
        bad = z.testzip()
        if bad or db_member not in z.namelist():
            target.unlink(missing_ok=True)
            raise HTTPException(500, "Backup verification failed; file discarded")
    return {"name": name, "size": target.stat().st_size, "attachments": len(files) + _db_file_count(url), "db_kind": kind, "verified": True,
            "path": str(target)}


def list_backups(out_dir: Path | None = None):
    out = out_dir or get_settings().backups_dir
    return [{"name": p.name, "size": p.stat().st_size, "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
            for p in sorted(out.glob("backup-*.zip"), reverse=True)]


def backup_path(name: str) -> Path:
    if not re.fullmatch(r"backup-\d{8}-\d{6}\.zip", name):
        raise HTTPException(404, "Not found")
    p = get_settings().backups_dir / name
    if not p.is_file():
        raise HTTPException(404, "Not found")
    return p


def restore_backup(zip_path: Path, target_db: Path, target_attachments: Path):
    """Restore a SQLite backup to a given (e.g. throw-away) location. Refuses to overwrite an existing database."""
    if target_db.exists():
        raise FileExistsError(f"{target_db} exists; refusing to overwrite. Move it aside first.")
    with zipfile.ZipFile(zip_path) as z:
        if z.testzip():
            raise ValueError("Backup zip is corrupt")
        man = json.loads(z.read("manifest.json"))
        if man["db_kind"] != "sqlite":
            raise ValueError("Only SQLite backups can be restored by this tool; use psql for database.sql")
        target_db.parent.mkdir(parents=True, exist_ok=True)
        target_db.write_bytes(z.read("database.sqlite"))
        for n in z.namelist():
            if n.startswith("attachments/") and not n.endswith("/"):
                rel = Path(n[len("attachments/"):])
                if ".." in rel.parts:
                    continue
                dest = target_attachments / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(n))
    return man


def _db_file_count(url: str) -> int:
    """Files stored inside the database travel with the database snapshot itself."""
    try:
        from sqlalchemy import create_engine, text
        eng = create_engine(url)
        with eng.connect() as c:
            return int(c.execute(text("SELECT COUNT(*) FROM stored_files")).scalar() or 0)
    except Exception:
        return 0
