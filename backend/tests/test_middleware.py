from fastapi.testclient import TestClient

from app.auth.sessions import create_session
from app.db import Base, engine
from app.main import app


def setup_module():
    # Dispose the connection pool so any WAL-poisoned connections left by
    # test_db.py (which opens the SQLCipher DB with plain sqlite3) are evicted
    # before we issue our first real query.
    engine.dispose()
    Base.metadata.create_all(engine)


def test_unauthed_request_401():
    with TestClient(app) as c:
        r = c.get("/api/entries")  # route not yet implemented but middleware runs first
        assert r.status_code == 401


def test_authed_request_passes_middleware():
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/entries", cookies={"session": sid})
    # Middleware allowed through; response is 404 (route missing) — NOT 401
    assert r.status_code != 401


def test_health_is_open():
    with TestClient(app) as c:
        r = c.get("/api/health")
    assert r.status_code == 200


def test_nonapi_path_bypasses_auth():
    with TestClient(app) as c:
        r = c.get("/some-static-thing")
    # Not under /api, middleware shouldn't check. FastAPI will 404 but not 401.
    assert r.status_code == 404


def test_expired_session_returns_401():
    from datetime import datetime, timedelta

    from app.db import SessionLocal
    from app.models.session import AppSession
    sid = create_session()
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        s.last_activity_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
    with TestClient(app) as c:
        r = c.get("/api/entries", cookies={"session": sid})
    assert r.status_code == 401
