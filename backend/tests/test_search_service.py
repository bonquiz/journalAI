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


from datetime import date

import numpy as _np
from fastapi import HTTPException

from app.models.entry import Entry
from app.services.embeddings import save_embedding_vector


def _reset_entries():
    with SessionLocal() as db:
        db.query(Entry).delete()
        db.commit()


def test_semantic_search_end_to_end():
    from app.services.search import semantic_search
    _reset_entries()
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.embed_model = "m1"
        db.add(Entry(id="e1", entry_date=date(2026, 4, 1), title="Regenbogen", content="Regenbögen."))
        db.add(Entry(id="e2", entry_date=date(2026, 4, 1), title="Auto", content="Neues Auto."))
        db.add(Entry(id="e3", entry_date=date(2026, 4, 1), title="Old", content="alt"))
        db.commit()
        save_embedding_vector(db, "e1", "m1", _np.array([1.0, 0.0, 0.0], dtype=_np.float32))
        save_embedding_vector(db, "e2", "m1", _np.array([0.0, 1.0, 0.0], dtype=_np.float32))
        save_embedding_vector(db, "e3", "old", _np.array([1.0, 0.0, 0.0], dtype=_np.float32))
        db.commit()

    intent = httpx.Response(200, json={"choices": [{"message": {"content": "Regenbogen"}}], "model": "c"})
    embed = httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0, 0.0]}], "model": "m1"})
    rerank = httpx.Response(200, json={
        "choices": [{"message": {"content": '{"results":[{"id":"e1","score":95,"reason":"Match"}]}'}}],
        "model": "c",
    })

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(side_effect=[intent, rerank])
        mock.post("/embeddings").mock(return_value=embed)
        result = semantic_search("Hey, Regenbogen?", top_k=5)

    assert result.status == "ok"
    assert [r.entry_id for r in result.results] == ["e1"]
    assert result.results[0].reason == "Match"


def test_semantic_search_not_configured_when_model_missing(monkeypatch):
    """not_configured only when DB, ENV, and OpenAI-default all fail.
    _DEFAULTS is frozen at module import time, so we patch it directly
    for the duration of the test."""
    from app.services import llm_client
    from app.services.search import semantic_search

    monkeypatch.setitem(llm_client._DEFAULTS, "embed", ("http://local.example/v1", "", ""))
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.embed_model = None
        s.embed_base_url = None
        db.commit()
    result = semantic_search("q")
    assert result.status == "not_configured"
    assert result.results == []
    # restore
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "m1"
        db.commit()


def test_semantic_search_indexing_when_no_embeddings_yet():
    from app.services.search import semantic_search
    _reset_entries()
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.embed_model = "m1"
        db.add(Entry(id="n", entry_date=date(2026, 4, 1), title="n", content="c"))
        db.commit()
    result = semantic_search("q")
    assert result.status == "indexing"
    assert result.progress["embedded"] == 0
    assert result.progress["total"] == 1


def test_semantic_search_filters_dimension_mismatches():
    """Corrupted/wrong-size vectors are dropped and counted; if ALL candidates
    are dropped, status=error (not 'indexing' — that would mask data bugs)."""
    from app.services.search import semantic_search
    _reset_entries()
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.embed_model = "m1"
        # All entries have model=m1 but wrong dimension (2 instead of 3)
        db.add(Entry(id="w1", entry_date=date(2026, 4, 1), title="w", content="c"))
        db.commit()
        save_embedding_vector(db, "w1", "m1", _np.array([1.0, 0.0], dtype=_np.float32))
        db.commit()

    intent = httpx.Response(200, json={"choices": [{"message": {"content": "x"}}], "model": "c"})
    embed = httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0, 0.0]}], "model": "m1"})

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(return_value=intent)
        mock.post("/embeddings").mock(return_value=embed)
        result = semantic_search("q")

    assert result.status == "error"
    assert result.results == []


def test_semantic_search_surfaces_embed_502():
    """If embed_text raises HTTPException(502), caller sees it — not silently swallowed."""
    from app.services.search import semantic_search
    _reset_entries()
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.embed_model = "m1"
        db.add(Entry(id="ok", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()
        save_embedding_vector(db, "ok", "m1", _np.array([1.0], dtype=_np.float32))
        db.commit()

    intent = httpx.Response(200, json={"choices": [{"message": {"content": "x"}}], "model": "c"})
    embed_fail = httpx.Response(503)

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(return_value=intent)
        mock.post("/embeddings").mock(return_value=embed_fail)
        import pytest
        with pytest.raises(HTTPException) as ei:
            semantic_search("q")
    assert ei.value.status_code == 502
