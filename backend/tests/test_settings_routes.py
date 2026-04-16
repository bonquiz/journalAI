from fastapi.testclient import TestClient

from app.auth.password import hash_password, verify_password
from app.auth.sessions import create_session
from app.crypto import unwrap_secret
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings

HEADERS = {"x-csrf-token": "t"}
def cookies(sid): return {"session": sid, "csrf": "t"}


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("oldpw")))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.commit()


def test_get_settings_masks_keys():
    # Seed with a wrapped key first via PUT
    sid = create_session()
    with TestClient(app) as c:
        c.put("/api/settings",
              json={"chat_api_key": "sk-verysecret1234",
                    "chat_base_url": "https://x/v1", "chat_model": "m"},
              cookies=cookies(sid), headers=HEADERS)
        g = c.get("/api/settings", cookies=cookies(sid)).json()
    assert g["chat_api_key_masked"] == "…1234"
    assert g["chat_base_url"] == "https://x/v1"
    assert g["chat_model"] == "m"


def test_put_wraps_key_in_db():
    sid = create_session()
    with TestClient(app) as c:
        c.put("/api/settings",
              json={"stt_api_key": "sk-secretstt"},
              cookies=cookies(sid), headers=HEADERS)
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        assert s.stt_api_key_wrapped is not None
        assert unwrap_secret(s.stt_api_key_wrapped) == "sk-secretstt"


def test_password_change_ok_and_invalidates():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post("/api/settings/password",
                   json={"old_password": "oldpw", "new_password": "newpw"},
                   cookies=cookies(sid), headers=HEADERS)
        assert r.status_code == 200
    # After invalidate_all, the session is gone; reading entries fails
    with TestClient(app) as c:
        r2 = c.get("/api/entries", cookies={"session": sid})
    assert r2.status_code == 401
    # Password was updated
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        assert verify_password("newpw", s.password_hash)
        # Restore for other tests
        s.password_hash = hash_password("oldpw")
        db.commit()


def test_password_change_wrong_old():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post("/api/settings/password",
                   json={"old_password": "wrong", "new_password": "x"},
                   cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 401


def test_tts_voice_and_speed_persist_and_roundtrip():
    sid = create_session()
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"tts_voice": "nova", "tts_speed": 1.25},
            cookies=cookies(sid),
            headers=HEADERS,
        )
        assert r.status_code == 200
        g = c.get("/api/settings", cookies=cookies(sid)).json()
    assert g["tts_voice"] == "nova"
    assert g["tts_speed"] == 1.25


def test_tts_voice_empty_string_clears_override():
    """Empty string PUT must reset the DB column to NULL (spec §5.4 last bullet)."""
    sid = create_session()
    with TestClient(app) as c:
        c.put("/api/settings", json={"tts_voice": "nova"},
              cookies=cookies(sid), headers=HEADERS)
        c.put("/api/settings", json={"tts_voice": "", "tts_speed": None},
              cookies=cookies(sid), headers=HEADERS)
        g = c.get("/api/settings", cookies=cookies(sid)).json()
    assert g["tts_voice"] is None
    assert g["tts_speed"] is None
