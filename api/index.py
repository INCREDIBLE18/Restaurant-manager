import os
import sys
from pathlib import Path

# Add project root and backend folder to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "backend"))

# Flag Vercel runtime for serverless file handling
os.environ.setdefault("VERCEL", "1")

# Import the FastAPI application
from app.main import app
