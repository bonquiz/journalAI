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
from app.services.search import RerankedResult, SemanticSearchResponse

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


def test_post_search_returns_results():
    sid = create_session()
    fake = SemanticSearchResponse(
        results=[RerankedResult(entry_id="e1", title="T", excerpt="E", score=90.0, reason="why")],
        status="ok",
    )
    with patch("app.routes.search.semantic_search", return_value=fake) as ss:
        with TestClient(app) as c:
            r = c.post(
                "/api/search",
                json={"query": "Regenbogen", "top_k": 5},
                cookies=cookies(sid),
                headers=HEADERS,
            )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["results"][0]["entry_id"] == "e1"
    ss.assert_called_once_with("Regenbogen", top_k=5)


def test_post_search_requires_auth():
    with TestClient(app) as c:
        r = c.post("/api/search", json={"query": "x"},
                   cookies={"csrf": "t"}, headers=HEADERS)
    assert r.status_code == 401


def test_post_search_requires_csrf():
    sid = create_session()
    with TestClient(app) as c:
        # Only session cookie, no csrf cookie/header
        r = c.post("/api/search", json={"query": "x"}, cookies={"session": sid})
    assert r.status_code == 403


def test_post_search_maps_502_on_embed_failure():
    sid = create_session()
    from fastapi import HTTPException
    with patch(
        "app.routes.search.semantic_search",
        side_effect=HTTPException(502, "Embedding-Server nicht erreichbar"),
    ):
        with TestClient(app) as c:
            r = c.post(
                "/api/search",
                json={"query": "x"},
                cookies=cookies(sid),
                headers=HEADERS,
            )
    assert r.status_code == 502
    assert "nicht erreichbar" in r.json()["detail"]


def _seed(with_emb: int, without_emb: int, model: str):
    with SessionLocal() as db:
        db.query(Entry).delete()
        for i in range(with_emb):
            db.add(Entry(
                id=f"w{i}", entry_date=date(2026, 4, 1), title=f"w{i}", content="c",
                embedding=pack_vector(np.array([1.0], dtype=np.float32)),
                embedding_model=model,
            ))
        for i in range(without_emb):
            db.add(Entry(id=f"n{i}", entry_date=date(2026, 4, 1), title=f"n{i}", content="c"))
        db.commit()


def test_search_status_counts():
    sid = create_session()
    _seed(3, 2, "m1")
    with TestClient(app) as c:
        r = c.get("/api/search/status", cookies={"session": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["embedded"] == 3
    assert body["pending"] == 2
    assert body["current_model"] == "m1"
    assert body["configured"] is True


def test_search_status_not_configured():
    sid = create_session()
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = None
        db.commit()
    with TestClient(app) as c:
        r = c.get("/api/search/status", cookies={"session": sid})
    assert r.json()["configured"] is False
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "m1"
        db.commit()
