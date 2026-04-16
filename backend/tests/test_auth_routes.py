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


def test_login_success_sets_cookie():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "testpw"})
    assert r.status_code == 200
    assert "session" in r.cookies


def test_login_wrong_password():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "bad"})
    assert r.status_code == 401


def test_logout_invalidates_cookie():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "testpw"})
        sid = r.cookies["session"]
        r2 = c.post("/api/auth/logout", cookies={"session": sid})
        assert r2.status_code == 200
        r3 = c.get("/api/entries", cookies={"session": sid})
    assert r3.status_code == 401


def test_login_with_totp_required_but_missing():
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.totp_secret = "JBSWY3DPEHPK3PXP"
        db.commit()
    try:
        with TestClient(app) as c:
            r = c.post("/api/auth/login", json={"password": "testpw"})
        assert r.status_code == 401
    finally:
        with SessionLocal() as db:
            db.get(AppSettings, 1).totp_secret = None
            db.commit()


def test_login_with_totp_valid():
    import pyotp
    secret = pyotp.random_base32()
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.totp_secret = secret
        db.commit()
    try:
        code = pyotp.TOTP(secret).now()
        with TestClient(app) as c:
            r = c.post("/api/auth/login", json={"password": "testpw", "totp": code})
        assert r.status_code == 200
    finally:
        with SessionLocal() as db:
            db.get(AppSettings, 1).totp_secret = None
            db.commit()
