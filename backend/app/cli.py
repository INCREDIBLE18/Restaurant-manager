"""Command line helpers:  python -m app.cli create-admin | backup | restore <zip> --db <path> --attachments <dir>"""
import argparse
import getpass
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ca = sub.add_parser("create-admin")
    ca.add_argument("--username", required=True)
    sub.add_parser("backup")
    rs = sub.add_parser("restore")
    rs.add_argument("zip")
    rs.add_argument("--db", required=True, help="target SQLite file (must not exist)")
    rs.add_argument("--attachments", required=True, help="target attachments folder")
    a = ap.parse_args()

    if a.cmd == "create-admin":
        from .core import hash_password
        from .db import SessionLocal
        from .models import User
        pw = getpass.getpass("Password (min 8 chars): ")
        if len(pw) < 8:
            sys.exit("Password too short")
        with SessionLocal() as db:
            if db.query(User).filter(User.username == a.username.lower()).first():
                sys.exit("User exists")
            db.add(User(username=a.username.lower(), password_hash=hash_password(pw), role="admin"))
            db.commit()
        print("Admin created.")
    elif a.cmd == "backup":
        from .backup import create_backup
        info = create_backup()
        print(f"Backup written and verified: {info['path']} ({info['size']} bytes, {info['attachments']} attachments)")
    elif a.cmd == "restore":
        from .backup import restore_backup
        man = restore_backup(Path(a.zip), Path(a.db), Path(a.attachments))
        print(f"Restored backup from {man['created']} to {a.db}. Point DATABASE_URL at it to use it.")


if __name__ == "__main__":
    main()
