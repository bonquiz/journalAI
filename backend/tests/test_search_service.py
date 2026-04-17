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


from types import SimpleNamespace


def _e(eid, title, content):
    return SimpleNamespace(id=eid, title=title, content=content)


def test_rerank_parses_valid_json():
    from app.services.search import rerank_results
    cands = [_e("e1", "Regenbogen-Traum", "Feld voller Regenbögen."),
             _e("e2", "Urlaub", "Strand und Wellen.")]
    j = '[{"id":"e1","score":92,"reason":"Match"},{"id":"e2","score":12,"reason":"Kein Bezug"}]'
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": j}}], "model": "chat"},
        ))
        out = rerank_results("Regenbogen", cands, top_k=2)
    assert [r.entry_id for r in out] == ["e1", "e2"]
    assert out[0].score == 92
    assert out[0].reason == "Match"


def test_rerank_falls_back_to_cosine_on_bad_json():
    from app.services.search import rerank_results
    cands = [_e("e1", "A", "a"), _e("e2", "B", "b")]
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "nicht json"}}], "model": "c"},
        ))
        out = rerank_results("q", cands, top_k=2)
    assert len(out) == 2
    assert all(r.reason is None for r in out)


def test_rerank_falls_back_on_http_error():
    from app.services.search import rerank_results
    cands = [_e("e1", "A", "a")]
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(side_effect=httpx.ConnectError("down"))
        out = rerank_results("q", cands, top_k=1)
    assert [r.entry_id for r in out] == ["e1"]
    assert out[0].reason is None


def test_rerank_returns_empty_for_empty_candidates():
    from app.services.search import rerank_results
    assert rerank_results("q", [], top_k=5) == []
