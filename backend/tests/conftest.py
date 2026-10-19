import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="rom_test_")
_pg = os.environ.get("TEST_DATABASE_URL", "")
if _pg:
    # Safety: the suite drops and recreates every table, so it may only ever touch a database named *_test.
    assert _pg.rsplit("/", 1)[-1].split("?")[0].endswith("_test"), "TEST_DATABASE_URL must point at a database whose name ends in _test"
os.environ["DATABASE_URL"] = _pg or f"sqlite:///{Path(_tmp, 'test.db').as_posix()}"
os.environ["DATA_DIR"] = _tmp
os.environ["SECRET_KEY"] = "test-secret"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app, init_defaults  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        init_defaults(s)
    s = SessionLocal()
    yield s
    s.close()


class Api:
    def __init__(self, client, token=None):
        self.c, self.h = client, ({"Authorization": f"Bearer {token}"} if token else {})

    def get(self, url, **kw):
        return self.c.get("/api/v1" + url, headers=self.h, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post("/api/v1" + url, json=json if json is not None else {}, headers=self.h, **kw)

    def put(self, url, json=None):
        return self.c.put("/api/v1" + url, json=json or {}, headers=self.h)

    def patch(self, url, json=None):
        return self.c.patch("/api/v1" + url, json=json or {}, headers=self.h)


@pytest.fixture()
def client(db):
    return TestClient(app)


@pytest.fixture()
def admin(client):
    r = client.post("/api/v1/auth/bootstrap", json={"username": "owner", "password": "password123", "full_name": "Owner"})
    assert r.status_code == 200, r.text
    return Api(client, r.json()["token"])


@pytest.fixture()
def staff(client, admin):
    assert admin.post("/users", {"username": "cashier", "password": "password123", "role": "staff"}).status_code == 200
    r = client.post("/api/v1/auth/login", json={"username": "cashier", "password": "password123"})
    return Api(client, r.json()["token"])


@pytest.fixture()
def accts(admin):
    return {a["name"]: a["id"] for a in admin.get("/accounts").json()}


def D(x):
    from decimal import Decimal
    return Decimal(str(x))
