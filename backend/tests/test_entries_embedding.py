from datetime import date
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import pack_vector

HEADERS = {"x-csrf-token": "t"}


def cookies(sid: str) -> dict[str, str]:
    return {"session": sid, "csrf": "t"}


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


def test_create_entry_schedules_embedding_task():
    sid = create_session()
    with patch("app.routes.entries.embed_entry_async") as mock_embed:
        with TestClient(app) as c:
            r = c.post(
                "/api/entries",
                json={"entry_date": "2026-04-01", "title": "x", "content": "y", "tags": []},
                cookies=cookies(sid),
                headers=HEADERS,
            )
    assert r.status_code == 201
    mock_embed.assert_called_once()
    assert mock_embed.call_args.args[0] == r.json()["id"]


def test_update_entry_content_invalidates_embedding():
    sid = create_session()
    with SessionLocal() as db:
        db.query(Entry).delete()
        db.add(Entry(
            id="upd1", entry_date=date(2026, 4, 1), title="old", content="old-content",
            embedding=pack_vector(np.array([1.0, 0.0], dtype=np.float32)),
            embedding_model="m1",
        ))
        db.commit()

    with patch("app.routes.entries.embed_entry_async") as mock_embed:
        with TestClient(app) as c:
            r = c.put(
                "/api/entries/upd1",
                json={"content": "NEW-content"},
                cookies=cookies(sid),
                headers=HEADERS,
            )
    assert r.status_code == 200
    with SessionLocal() as db:
        e = db.get(Entry, "upd1")
        assert e.embedding is None
        assert e.embedding_model is None
    mock_embed.assert_called_once_with("upd1")


def test_update_entry_tags_only_keeps_embedding():
    sid = create_session()
    with SessionLocal() as db:
        db.query(Entry).filter(Entry.id == "upd2").delete()
        db.add(Entry(
            id="upd2", entry_date=date(2026, 4, 1), title="t", content="c",
            embedding=pack_vector(np.array([1.0, 0.0], dtype=np.float32)),
            embedding_model="m1",
        ))
        db.commit()

    with patch("app.routes.entries.embed_entry_async") as mock_embed:
        with TestClient(app) as c:
            r = c.put(
                "/api/entries/upd2",
                json={"tags": ["happy"]},
                cookies=cookies(sid),
                headers=HEADERS,
            )
    assert r.status_code == 200
    with SessionLocal() as db:
        e = db.get(Entry, "upd2")
        assert e.embedding is not None
        assert e.embedding_model == "m1"
    mock_embed.assert_not_called()
