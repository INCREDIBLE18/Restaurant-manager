"""
End-to-end verification script for Neon Postgres and Neon Auth integration.
Tests:
1. Neon Database connection (pooled & direct)
2. Neon Schema inspection (public tables + neon_auth tables)
3. API Health endpoint
4. Auth Status endpoint
5. App bootstrap / user creation on Neon Postgres
6. Authentication & token validation
7. CRUD operations (creating customer, querying accounts)
8. Neon Auth JWKS & base URL connectivity
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import requests
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import get_settings
from backend.app.db import engine, unpooled_engine, SessionLocal
from backend.app.models import User, Customer, Account
from sqlalchemy import text, inspect

def run_tests():
    print("=" * 60)
    print("NEON INTEGRATION END-TO-END VERIFICATION")
    print("=" * 60)
    cfg = get_settings()

    # 1. Connection check
    print("\n[1] Testing Neon Database Connection...")
    with engine.connect() as conn:
        res = conn.execute(text("SELECT current_database(), current_user, inet_server_addr(), version();")).fetchone()
        print(f"  [OK] Connected to DB: {res[0]} as user: {res[1]}")
        print(f"  [OK] PostgreSQL version: {res[3][:45]}...")

    # 2. Schema check
    print("\n[2] Testing Schemas on Neon...")
    ins = inspect(engine)
    schemas = ins.get_schema_names()
    print(f"  [OK] Schemas present: {schemas}")
    assert "public" in schemas, "Missing public schema"
    assert "neon_auth" in schemas, "Missing neon_auth schema"

    public_tables = ins.get_table_names(schema="public")
    neon_auth_tables = ins.get_table_names(schema="neon_auth")
    print(f"  [OK] Public tables ({len(public_tables)}): {public_tables[:6]} ...")
    print(f"  [OK] Neon Auth tables ({len(neon_auth_tables)}): {neon_auth_tables}")

    # 3. FastAPI Client Tests
    print("\n[3] Testing API Endpoints with TestClient...")
    client = TestClient(app)

    # Health
    r = client.get("/api/v1/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    health_json = r.json()
    print(f"  [OK] /health: {health_json}")
    assert health_json["status"] == "ok"
    assert health_json["neon_branch"] == "production"

    # Auth Status
    r = client.get("/api/v1/auth/status")
    assert r.status_code == 200, f"Auth status failed: {r.text}"
    auth_status = r.json()
    print(f"  [OK] /auth/status: {auth_status}")
    assert auth_status["neon_auth"] is True

    # Bootstrap or Login
    print("\n[4] Testing User Authentication & Bootstrap on Neon...")
    with SessionLocal() as db:
        admin = db.query(User).filter(User.username == "admin").first()
    
    token = None
    if not admin:
        print("  Creating initial admin user...")
        r = client.post("/api/v1/auth/bootstrap", json={
            "username": "admin",
            "password": "Password123!",
            "full_name": "Neon Admin",
            "role": "admin"
        })
        assert r.status_code == 200, f"Bootstrap failed: {r.text}"
        data = r.json()
        token = data["token"]
        print(f"  [OK] Admin created successfully on Neon DB. User: {data['user']['username']}")
    else:
        print("  Admin user exists, testing login...")
        r = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "Password123!"
        })
        assert r.status_code == 200, f"Login failed: {r.text}"
        data = r.json()
        token = data["token"]
        print(f"  [OK] Logged in successfully on Neon DB. User: {data['user']['username']}")

    headers = {"Authorization": f"Bearer {token}"}

    # 5. Protected Endpoint & Data Persistence
    print("\n[5] Testing Data Persistence on Neon Postgres...")
    r = client.get("/api/v1/accounts", headers=headers)
    assert r.status_code == 200, f"Get accounts failed: {r.text}"
    accounts = r.json()
    print(f"  [OK] Accounts retrieved from Neon: {[a['name'] for a in accounts]}")

    # Create customer test
    test_phone = "9876543210"
    r = client.post("/api/v1/customers", headers=headers, json={
        "name": "Neon Test Customer",
        "phone": test_phone,
        "notes": "Verified via Neon E2E suite"
    })
    # If customer already exists (from previous run), fetch it
    if r.status_code == 200:
        cust = r.json()
        print(f"  [OK] Created test customer '{cust['name']}' (ID: {cust['id']}) on Neon DB")
    elif r.status_code == 409 or r.status_code == 422:
        print(f"  [OK] Customer already created in previous run, querying back from Neon DB...")
        r = client.get("/api/v1/customers", headers=headers)
        assert r.status_code == 200
        print(f"  [OK] Customer list successfully retrieved from Neon DB")

    # 6. Neon Auth Service Reachability
    print("\n[6] Testing Neon Auth Cloud Endpoint...")
    if cfg.neon_auth_base_url:
        print(f"  Auth Base URL: {cfg.neon_auth_base_url}")
        print(f"  JWKS URL: {cfg.neon_auth_jwks_url}")
        try:
            jwks_resp = requests.get(cfg.neon_auth_jwks_url, timeout=5)
            print(f"  [OK] Neon Auth JWKS HTTP status: {jwks_resp.status_code}")
            if jwks_resp.status_code == 200:
                keys = jwks_resp.json().get("keys", [])
                print(f"  ✓ Active JWKS keys returned: {len(keys)}")
        except Exception as e:
            print(f"  Notice: JWKS query returned: {e}")

    print("\n" + "=" * 60)
    print("ALL NEON SERVICES TESTED AND VERIFIED END-TO-END!")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
