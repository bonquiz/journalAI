from datetime import date

import httpx
import numpy as np
import respx

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.models.entry import Entry
from app.models.entry_embedding import EntryEmbedding
from app.models.settings import AppSettings
from app.services.embeddings import save_embedding_vector, unpack_vector


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"), embed_model="m1"))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(EntryEmbedding).delete()
        db.query(Entry).delete()
        db.query(AppSettings).delete()
        db.commit()


def _reset_entries():
    with SessionLocal() as db:
        db.query(EntryEmbedding).delete()
        db.query(Entry).delete()
        db.commit()


def test_embed_entry_populates_embedding():
    from app.services.embedding_jobs import embed_entry_async
    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="e1", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}], "model": "m1"},
        ))
        embed_entry_async("e1")

    with SessionLocal() as db:
        row = db.get(EntryEmbedding, ("e1", "m1"))
        assert row is not None
        assert unpack_vector(row.vector).shape == (3,)


def test_embed_entry_skips_missing_entry():
    from app.services.embedding_jobs import embed_entry_async
    _reset_entries()
    embed_entry_async("missing")  # must not raise


def test_embed_entry_tolerates_provider_failure():
    from app.services.embedding_jobs import embed_entry_async
    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="e2", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(500))
        embed_entry_async("e2")  # must not raise

    with SessionLocal() as db:
        assert db.get(EntryEmbedding, ("e2", "m1")) is None


def test_embed_entry_skips_persist_if_model_changed_since_call():
    """Race guard: settings.embed_model was flipped between get_client() and the
    DB write. The result is discarded — backfill will pick up with the new model."""
    from app.services.embedding_jobs import embed_entry_async
    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="e3", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()

    # Provider responds with old model name, but settings has already moved on.
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.1, 0.2]}], "model": "old-model"},
        ))
        # Flip settings before embed_entry_async writes back
        with SessionLocal() as db:
            db.get(AppSettings, 1).embed_model = "new-model"
            db.commit()
        embed_entry_async("e3")

    with SessionLocal() as db:
        # Result discarded — no row for "new-model"
        assert db.get(EntryEmbedding, ("e3", "new-model")) is None

    # restore for later tests
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "m1"
        db.commit()


def test_embed_dimensions_set_only_once():
    from app.services.embedding_jobs import embed_entry_async
    _reset_entries()
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.embed_dimensions = None
        s.embed_model = "m1"
        db.add(Entry(id="d1", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}], "model": "m1"},
        ))
        embed_entry_async("d1")

    with SessionLocal() as db:
        assert db.get(AppSettings, 1).embed_dimensions == 3

    # Second call with DIFFERENT dimension must NOT overwrite
    with SessionLocal() as db:
        db.add(Entry(id="d2", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.1, 0.2, 0.3, 0.4, 0.5]}], "model": "m1"},
        ))
        embed_entry_async("d2")

    with SessionLocal() as db:
        # Guard: still 3, warning should be logged (not enforced in test)
        assert db.get(AppSettings, 1).embed_dimensions == 3


import asyncio as _a  # noqa: E402


def test_backfill_fills_missing_and_skips_matching_model():
    from app.services.embedding_jobs import _do_backfill

    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="a", entry_date=date(2026, 4, 1), title="a", content="c"))
        db.add(Entry(id="b", entry_date=date(2026, 4, 1), title="b", content="c"))
        db.add(Entry(id="c", entry_date=date(2026, 4, 1), title="c", content="c"))
        db.flush()
        save_embedding_vector(db, "b", "old", np.array([0.0, 1.0], dtype=np.float32))
        save_embedding_vector(db, "c", "m1", np.array([1.0, 0.0], dtype=np.float32))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        route = mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.5, 0.5]}], "model": "m1"},
        ))
        _a.run(_do_backfill())

    assert route.call_count == 2  # a + b, not c


def test_reindex_clears_rows_then_refills_under_same_lock():
    from app.services.embedding_jobs import _do_reindex

    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="z", entry_date=date(2026, 4, 1), title="z", content="c"))
        db.flush()
        save_embedding_vector(db, "z", "m1", np.array([1.0], dtype=np.float32))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.9, 0.1]}], "model": "m1"},
        ))
        _a.run(_do_reindex())

    with SessionLocal() as db:
        row = db.get(EntryEmbedding, ("z", "m1"))
        assert row is not None
        assert unpack_vector(row.vector).shape == (2,)


def test_backoff_on_provider_rate_limit():
    """When embed_entry_async raises ProviderRateLimited, _embed_one_with_backoff
    retries with exponential backoff. We patch embed_entry_async directly to
    isolate the runner's backoff — the OpenAI SDK does its own internal retries
    on 429 which would otherwise swallow the signal before we see it."""
    from unittest.mock import patch

    import app.services.embedding_jobs as jobs
    from app.services.embeddings import ProviderRateLimited

    calls = {"n": 0}

    def fake_embed(entry_id: str) -> None:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ProviderRateLimited("simulated 429")
        # third call succeeds

    old_steps = jobs.BACKOFF_STEPS
    jobs.BACKOFF_STEPS = (0.01, 0.01, 0.01)
    try:
        with patch.object(jobs, "embed_entry_async", fake_embed):
            _a.run(jobs._embed_one_with_backoff("any-id"))
    finally:
        jobs.BACKOFF_STEPS = old_steps

    assert calls["n"] == 3  # 2 × 429 + 1 success


def test_backoff_gives_up_after_all_retries():
    """After len(BACKOFF_STEPS) + 1 = 4 attempts of ProviderRateLimited, the
    runner logs a warning and returns without raising. The entry stays
    unembedded; a later backfill pass will try again."""
    from unittest.mock import patch

    import app.services.embedding_jobs as jobs
    from app.services.embeddings import ProviderRateLimited

    calls = {"n": 0}

    def always_429(entry_id: str) -> None:
        calls["n"] += 1
        raise ProviderRateLimited("persistent 429")

    old_steps = jobs.BACKOFF_STEPS
    jobs.BACKOFF_STEPS = (0.01, 0.01, 0.01)
    try:
        with patch.object(jobs, "embed_entry_async", always_429):
            _a.run(jobs._embed_one_with_backoff("any-id"))
    finally:
        jobs.BACKOFF_STEPS = old_steps

    assert calls["n"] == 4  # initial + 3 retries


def test_request_coalescing():
    """Multiple request_backfill() calls while a job is running collapse to one.
    request_reindex() supersedes a queued backfill."""
    from app.services.embedding_jobs import (
        _state,
        request_backfill,
        request_reindex,
    )
    # Direct state inspection — runner isn't started in this test
    _state.pending_backfill = False
    _state.pending_reindex = False
    _state.running = False

    request_backfill()
    request_backfill()
    request_backfill()
    assert _state.pending_backfill is True
    assert _state.pending_reindex is False

    request_reindex()
    assert _state.pending_reindex is True
    # pending_backfill becomes irrelevant — reindex does a full pass anyway
