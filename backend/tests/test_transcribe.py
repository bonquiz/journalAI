import io

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


def test_transcribe_requires_auth():
    # Unauthenticated POST hits CSRF middleware first (no csrf cookie) → 403.
    # A request with a CSRF cookie but no session cookie → 401.
    audio = io.BytesIO(b"fake-wav")
    with TestClient(app) as c:
        r = c.post(
            "/api/transcribe",
            files={"file": ("a.wav", audio, "audio/wav")},
            cookies={"csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 401


def test_transcribe_returns_text():
    sid = create_session()
    audio = io.BytesIO(b"\\x00\\x00RIFF...fake wav...")
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/audio/transcriptions").mock(
            return_value=httpx.Response(200, json={"text": "hallo welt"})
        )
        with TestClient(app) as c:
            r = c.post(
                "/api/transcribe",
                files={"file": ("a.wav", audio, "audio/wav")},
                cookies={"session": sid, "csrf": "t"},
                headers={"x-csrf-token": "t"},
            )
    assert r.status_code == 200
    assert r.json()["transcript"] == "hallo welt"


def test_transcribe_rejects_too_large():
    sid = create_session()
    # 30 MB > default 25 MB max
    audio = io.BytesIO(b"\\x00" * (30 * 1024 * 1024))
    with TestClient(app) as c:
        r = c.post(
            "/api/transcribe",
            files={"file": ("big.wav", audio, "audio/wav")},
            cookies={"session": sid, "csrf": "t"},
            headers={"x-csrf-token": "t"},
        )
    assert r.status_code == 413
