import os
import sys
from pathlib import Path

# Add project root and backend folder to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend"))

# Flag Vercel runtime
os.environ.setdefault("VERCEL", "1")

from backend.app.main import app
