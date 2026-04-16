import httpx
import respx
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


def test_health_is_public_and_lists_endpoints():
    with respx.mock() as mock:
        mock.head("https://api.openai.com/v1").mock(return_value=httpx.Response(200))
        with TestClient(app) as c:
            r = c.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["endpoints"].keys()) == {"stt", "chat", "embed", "tts"}


def test_health_handles_unreachable():
    # No respx mock = real HEAD goes out but will timeout/fail fast if we stub nothing.
    # Instead, install a mock that returns 500 from both HEAD and /models.
    with respx.mock() as mock:
        mock.head("https://api.openai.com/v1").mock(return_value=httpx.Response(500))
        mock.get("https://api.openai.com/v1/models").mock(return_value=httpx.Response(500))
        with TestClient(app) as c:
            r = c.get("/api/health")
    assert r.status_code == 200
    assert all(v is False for v in r.json()["endpoints"].values())


def test_session_ping_requires_auth():
    with TestClient(app) as c:
        r = c.post("/api/session/ping", cookies={"csrf": "t"}, headers={"x-csrf-token": "t"})
    assert r.status_code == 401


def test_session_ping_with_auth():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post("/api/session/ping",
                   cookies={"session": sid, "csrf": "t"},
                   headers={"x-csrf-token": "t"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
