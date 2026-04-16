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
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.commit()


def test_post_without_csrf_is_403():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post("/api/auth/logout", cookies={"session": sid})
    assert r.status_code == 403


def test_post_with_matching_header_and_cookie_passes():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post(
            "/api/auth/logout",
            cookies={"session": sid, "csrf": "t123"},
            headers={"X-CSRF-Token": "t123"},
        )
    assert r.status_code == 200


def test_post_mismatched_csrf_is_403():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post(
            "/api/auth/logout",
            cookies={"session": sid, "csrf": "abc"},
            headers={"X-CSRF-Token": "def"},
        )
    assert r.status_code == 403


def test_login_is_exempt_and_sets_csrf_cookie():
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json={"password": "pw"})
    assert r.status_code == 200
    assert "csrf" in r.cookies


def test_get_requests_bypass_csrf():
    with TestClient(app) as c:
        r = c.get("/api/health")
    assert r.status_code == 200  # no csrf needed for GET
