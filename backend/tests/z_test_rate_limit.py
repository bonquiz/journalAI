"""Rate limiting regression test for /auth/login endpoint."""
from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("testpw")))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is not None:
            db.delete(s)
            db.commit()


def test_login_rate_limited():
    """5/minute limit — 6th bad attempt should return 429."""
    with TestClient(app) as c:
        for _ in range(5):
            c.post("/api/auth/login", json={"password": "bad"})
        r = c.post("/api/auth/login", json={"password": "bad"})
    assert r.status_code == 429
