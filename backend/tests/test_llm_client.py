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
