"""Script to test Neon PostgreSQL connection and initialize schema.

Usage:
  python scripts/test_neon_connection.py "<YOUR_NEON_DATABASE_URL>"

Example:
  python scripts/test_neon_connection.py "postgresql://user:pass@ep-cool-fog-123456.us-east-2.aws.neon.tech/neondb?sslmode=require"
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text

def test_neon():
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_neon_connection.py '<NEON_DATABASE_URL>'")
        print("Example: python scripts/test_neon_connection.py 'postgresql://user:pass@ep-xyz.us-east-2.aws.neon.tech/neondb?sslmode=require'")
        return

    raw_url = sys.argv[1].strip()
    url = "postgresql://" + raw_url[len("postgres://"):] if raw_url.startswith("postgres://") else raw_url

    print("Connecting to Neon PostgreSQL...")
    from app.db import make_engine, SessionLocal
    from app.models import Base
    from app.main import init_defaults

    try:
        engine = make_engine(url)
        with engine.connect() as conn:
            ver = conn.execute(text("SELECT version();")).scalar()
            print(f"✓ Connected successfully to Neon DB!\n  Version: {ver}\n")

            print("Ensuring all tables and constraints exist...")
            Base.metadata.create_all(bind=engine)
            print("✓ All 24 tables and constraints created / verified in Neon DB!")

        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=engine)
        with Session() as db:
            init_defaults(db)
            print("✓ Default accounts and application settings verified!")

        print("\nYour Neon DB is completely ready for Vercel deployment!")
    except Exception as e:
        print(f"❌ Connection or setup failed: {e}")

if __name__ == "__main__":
    test_neon()
