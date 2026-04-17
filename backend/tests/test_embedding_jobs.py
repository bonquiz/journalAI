from datetime import date

import httpx
import respx

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import unpack_vector


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw"), embed_model="m1"))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(Entry).delete()
        db.query(AppSettings).delete()
        db.commit()


def _reset_entries():
    with SessionLocal() as db:
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
        e = db.get(Entry, "e1")
        assert e.embedding is not None
        assert e.embedding_model == "m1"
        assert e.embedding_updated_at is not None
        assert unpack_vector(e.embedding).shape == (3,)


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
        assert db.get(Entry, "e2").embedding is None


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
        e = db.get(Entry, "e3")
        # Result discarded (or persisted with old model but NOT marked under new)
        assert e.embedding_model != "new-model"

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
