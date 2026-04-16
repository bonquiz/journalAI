import httpx
import respx
from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings

HEADERS = {"x-csrf-token": "t"}


def cookies(sid: str) -> dict[str, str]:
    return {"session": sid, "csrf": "t"}


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"),
                              tts_voice="alloy", tts_speed=1.0))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.commit()


def test_route_requires_auth():
    with TestClient(app) as c:
        r = c.post("/api/tts", json={"text": "Hallo."},
                   cookies={"csrf": "t"}, headers=HEADERS)
    assert r.status_code == 401


def test_route_returns_audio_mpeg():
    sid = create_session()
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(
            return_value=httpx.Response(200, content=b"ID3FAKE",
                                        headers={"Content-Type": "audio/mpeg"})
        )
        with TestClient(app) as c:
            r = c.post(
                "/api/tts",
                json={"text": "Hallo Welt."},
                cookies=cookies(sid),
                headers=HEADERS,
            )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mpeg")
    assert r.content == b"ID3FAKE"


def test_route_rejects_empty_text():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post(
            "/api/tts",
            json={"text": ""},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 422


def test_route_rejects_text_over_20000_chars():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post(
            "/api/tts",
            json={"text": "x" * 20001},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 422


def test_route_accepts_voice_and_speed_override():
    sid = create_session()
    captured = []

    def _h(request):
        import json as _json
        captured.append(_json.loads(request.content))
        return httpx.Response(200, content=b"X", headers={"Content-Type": "audio/mpeg"})

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(side_effect=_h)
        with TestClient(app) as c:
            r = c.post(
                "/api/tts",
                json={"text": "Hi.", "voice": "echo", "speed": 1.5},
                cookies=cookies(sid),
                headers=HEADERS,
            )
    assert r.status_code == 200
    assert captured[0]["voice"] == "echo"
    assert captured[0]["speed"] == 1.5


def test_route_maps_upstream_401_to_502():
    sid = create_session()
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(
            return_value=httpx.Response(401, json={"error": "bad key"})
        )
        with TestClient(app) as c:
            r = c.post("/api/tts", json={"text": "Hi."},
                       cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 502
    assert "auth" in r.json()["detail"].lower() or "401" in r.json()["detail"]


def test_route_maps_upstream_404_to_502():
    sid = create_session()
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(
            return_value=httpx.Response(404, json={"error": "model not found"})
        )
        with TestClient(app) as c:
            r = c.post("/api/tts", json={"text": "Hi."},
                       cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 502
    assert "404" in r.json()["detail"] or "nicht gefunden" in r.json()["detail"].lower()


def test_route_maps_upstream_5xx_to_502():
    sid = create_session()
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(return_value=httpx.Response(503))
        with TestClient(app) as c:
            r = c.post("/api/tts", json={"text": "Hi."},
                       cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 502


def test_route_maps_network_failure_to_502():
    sid = create_session()
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(side_effect=httpx.ConnectError("boom"))
        with TestClient(app) as c:
            r = c.post("/api/tts", json={"text": "Hi."},
                       cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 502


def test_route_rate_limit_returns_429():
    from app.security.rate_limit import limiter
    limiter.reset()
    sid = create_session()
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/speech").mock(
            return_value=httpx.Response(200, content=b"OK",
                                        headers={"Content-Type": "audio/mpeg"})
        )
        with TestClient(app) as c:
            for _ in range(30):
                c.post("/api/tts", json={"text": "Hi."},
                       cookies=cookies(sid), headers=HEADERS)
            r = c.post("/api/tts", json={"text": "Hi."},
                       cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 429
    limiter.reset()
