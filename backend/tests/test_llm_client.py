from app.auth.password import hash_password
from app.crypto import wrap_secret
from app.db import Base, SessionLocal, engine
from app.models.settings import AppSettings
from app.services.llm_client import get_client


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(
            id=1, password_hash=hash_password("pw"),
            chat_base_url="https://example.test/v1",
            chat_api_key_wrapped=wrap_secret("sk-test"),
            chat_model="gpt-test",
        ))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.commit()


def test_chat_client_uses_db_settings():
    client, model = get_client("chat")
    assert "example.test/v1" in str(client.base_url)
    assert client.api_key == "sk-test"
    assert model == "gpt-test"


def test_fallback_to_env_when_db_empty():
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.stt_base_url = None
        s.stt_api_key_wrapped = None
        s.stt_model = None
        db.commit()
    client, model = get_client("stt")
    assert "openai.com" in str(client.base_url)
    assert model == "whisper-1"


def test_unknown_capability_raises():
    import pytest
    with pytest.raises((KeyError, ValueError)):
        get_client("bogus")  # type: ignore[arg-type]


def test_openai_api_key_fallback_for_openai_base_url(monkeypatch):
    """When STT has no specific key but base URL is OpenAI, use OPENAI_API_KEY."""
    from app.config import settings as env
    monkeypatch.setattr(env, "openai_api_key", "sk-shared-master")
    monkeypatch.setattr(env, "stt_api_key", "")  # no capability-specific key
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.stt_base_url = None
        s.stt_api_key_wrapped = None
        s.stt_model = None
        db.commit()
    client, _ = get_client("stt")
    assert client.api_key == "sk-shared-master"


def test_openai_api_key_not_used_for_non_openai_url(monkeypatch):
    """Shared OPENAI key must NOT leak into local/non-OpenAI endpoints."""
    from app.config import settings as env
    monkeypatch.setattr(env, "openai_api_key", "sk-shared-master")
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.embed_base_url = "http://ollama:11434/v1"
        s.embed_api_key_wrapped = None
        s.embed_model = "bge-m3"
        db.commit()
    client, _ = get_client("embed")
    assert client.api_key == "unused"  # falls back to placeholder, not shared key
