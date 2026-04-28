from datetime import date

import numpy as np
from fastapi.testclient import TestClient

from app.auth.password import hash_password, verify_password
from app.auth.sessions import create_session
from app.crypto import unwrap_secret
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.entry import Entry
from app.models.entry_embedding import EntryEmbedding
from app.models.settings import AppSettings
from app.services.embeddings import pack_vector

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
    assert "coach_presets" in g
    assert {p["key"] for p in g["coach_presets"]} == {"therapist", "coach", "stoic", "spiritual"}
    assert g["default_coach_preset_key"] == "therapist"


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


def test_settings_put_returns_full_payload():
    """Response now mirrors GET /api/settings (full SettingsOut) instead of {ok}."""
    sid = create_session()
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "initial"
        db.commit()
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"embed_model": "initial"},  # no real change
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    # Must include full SettingsOut-like shape
    assert "embed_model" in body
    assert "tts_voice" in body
    assert body["embed_model"] == "initial"
    assert "warning" not in body


def test_settings_put_warns_on_embed_model_change_with_existing_entries():
    sid = create_session()
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "old-model"
        db.query(Entry).delete()
        entry = Entry(id="mm1", entry_date=date(2026, 4, 1), title="t", content="c")
        db.add(entry)
        db.flush()
        vec = pack_vector(np.array([0.1], dtype=np.float32))
        db.add(EntryEmbedding(
            entry_id="mm1", model="old-model", dim=1, vector=vec,
        ))
        db.commit()

    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"embed_model": "new-model"},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["warning"] == "embedding_model_mismatch"
    assert body["embedding_mismatch"]["old_model"] == "old-model"
    assert body["embedding_mismatch"]["new_model"] == "new-model"
    assert body["embedding_mismatch"]["affected_entries"] == 1
    assert body["embed_model"] == "new-model"  # still saved
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).embed_model == "new-model"


def test_settings_put_no_warning_when_no_existing_entries():
    sid = create_session()
    with SessionLocal() as db:
        db.query(Entry).delete()
        db.get(AppSettings, 1).embed_model = "m1"
        db.commit()
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"embed_model": "m2"},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    assert "warning" not in r.json()
