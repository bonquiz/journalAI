"""GET /api/settings muss resolved_base_url / resolved_model pro
Capability zurückgeben, sodass das Frontend den effektiven Wert
anzeigen kann, wenn das DB-Feld leer ist.
"""
from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings

HEADERS = {"x-csrf-token": "t"}


def setup_module(module):
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("testpw")))
        db.commit()


def cookies(sid):
    return {"session": sid, "csrf": "t"}


def test_get_settings_returns_resolved_chat(monkeypatch):
    # Patch the _DEFAULTS snapshot so resolved_* helpers see our env values.
    from app.services import llm_client
    monkeypatch.setitem(llm_client._DEFAULTS, "chat",
                        ("http://ollama:11434/v1", "", "qwen2.5:7b-instruct-q4_K_M"))

    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/settings", cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["chat_base_url"] in (None, "")
    assert body["chat_resolved_base_url"] == "http://ollama:11434/v1"
    assert body["chat_resolved_model"] == "qwen2.5:7b-instruct-q4_K_M"


def test_get_settings_resolved_fields_present_for_all_capabilities():
    """All four capabilities must expose resolved_base_url and resolved_model."""
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/settings", cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    for cap in ("stt", "chat", "embed", "tts"):
        assert f"{cap}_resolved_base_url" in body, f"missing {cap}_resolved_base_url"
        assert f"{cap}_resolved_model" in body, f"missing {cap}_resolved_model"
