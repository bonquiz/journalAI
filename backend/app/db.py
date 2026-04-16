"""SQLCipher-backed SQLAlchemy engine + declarative Base.

The cipher is AES-256-CBC via SQLCipher 4.x, with a kdf_iter of 64_000
(SQLCipher default; increase if you want more PBKDF2 rounds at open time).
Engine URL: sqlite+pysqlcipher://:<key>@/<path>?cipher=...&kdf_iter=...
"""
import os
from urllib.parse import quote

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _engine_url() -> str:
    # Ensure parent directory for DB file exists (important for tests using tmp paths)
    db_path = settings.db_path
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    # URL-encode the key so non-ASCII chars don't break the URL (hex is ASCII-safe anyway)
    key = quote(settings.db_encryption_key, safe="")
    return (
        f"sqlite+pysqlcipher://:{key}@/{db_path}"
        f"?cipher=aes-256-cbc&kdf_iter=64000"
    )


engine = create_engine(
    _engine_url(),
    future=True,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_pragmas(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
