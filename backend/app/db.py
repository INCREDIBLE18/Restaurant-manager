from decimal import Decimal

from sqlalchemy import Numeric, String, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import get_settings


class Dec(TypeDecorator):
    """Decimal-safe column: NUMERIC on PostgreSQL, canonical decimal string on SQLite
    (SQLite NUMERIC would silently coerce to binary float). All aggregation is done in
    Python Decimal so both back-ends behave identically."""

    impl = Numeric(16, 3)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(40))
        return dialect.type_descriptor(Numeric(16, 3))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        value = Decimal(str(value))
        return format(value, "f") if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(str(value))


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    url = url or get_settings().database_url
    # Normalize postgres:// to postgresql:// (Neon / Supabase / cloud providers)
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Optimized pooling for Neon serverless Postgres
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 300
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10

    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _fk(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
