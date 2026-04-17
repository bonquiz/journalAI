import httpx
import respx

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
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


def test_extract_search_intent_reduces_conversational_query():
    from app.services.search import extract_search_intent
    raw = "Hey, ich habe doch mal darüber gesprochen, dass ich einen Traum mit Regenbögen hatte."
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "Traum mit Regenbögen"}}], "model": "gpt-4o-mini"},
        ))
        assert extract_search_intent(raw) == "Traum mit Regenbögen"


def test_extract_search_intent_falls_back_on_error():
    from app.services.search import extract_search_intent
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(side_effect=httpx.ConnectError("down"))
        assert extract_search_intent("raw query") == "raw query"
