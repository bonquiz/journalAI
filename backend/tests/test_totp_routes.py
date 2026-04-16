import pyotp
from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"),
                             totp_secret=None, totp_pending_secret=None))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s:
            db.delete(s)
            db.commit()


def test_setup_returns_secret_and_qr():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post("/api/auth/totp/setup", cookies={"session": sid})
    assert r.status_code == 200
    body = r.json()
    assert "secret" in body
    assert "qr_png_base64" in body
    assert "provisioning_uri" in body
    # Pending secret persisted server-side
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).totp_pending_secret == body["secret"]


def test_confirm_without_setup_fails():
    # Ensure no pending secret
    with SessionLocal() as db:
        db.get(AppSettings, 1).totp_pending_secret = None
        db.commit()
    sid = create_session()
    with TestClient(app) as c:
        r = c.post("/api/auth/totp/confirm", json={"code": "123456"},
                   cookies={"session": sid})
    assert r.status_code == 400


def test_confirm_with_invalid_code_fails():
    sid = create_session()
    with TestClient(app) as c:
        c.post("/api/auth/totp/setup", cookies={"session": sid})
        r = c.post("/api/auth/totp/confirm", json={"code": "000000"},
                   cookies={"session": sid})
    assert r.status_code == 400


def test_confirm_activates_and_clears_pending():
    sid = create_session()
    with TestClient(app) as c:
        setup = c.post("/api/auth/totp/setup", cookies={"session": sid}).json()
        code = pyotp.TOTP(setup["secret"]).now()
        r = c.post("/api/auth/totp/confirm", json={"code": code},
                   cookies={"session": sid})
    assert r.status_code == 200
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        assert s.totp_secret == setup["secret"]
        assert s.totp_pending_secret is None
