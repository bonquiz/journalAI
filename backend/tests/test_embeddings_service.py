from datetime import date
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
import respx
from fastapi import HTTPException

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.models.settings import AppSettings
from app.services.embeddings import cosine_similarity, pack_vector, unpack_vector


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


def test_pack_unpack_roundtrip():
    vec = np.array([0.1, -0.2, 0.3, 0.0], dtype=np.float32)
    blob = pack_vector(vec)
    back = unpack_vector(blob)
    assert back.dtype == np.float32
    assert back.shape == (4,)
    np.testing.assert_array_equal(back, vec)


def test_cosine_similarity_identical():
    q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    m = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    scores = cosine_similarity(q, m)
    assert abs(scores[0] - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    q = np.array([1.0, 0.0], dtype=np.float32)
    m = np.array([[0.0, 1.0]], dtype=np.float32)
    assert abs(cosine_similarity(q, m)[0]) < 1e-6


def test_cosine_similarity_batch():
    q = np.array([1.0, 0.0], dtype=np.float32)
    m = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]], dtype=np.float32)
    scores = cosine_similarity(q, m)
    assert scores.shape == (3,)
    assert abs(scores[0] - 1.0) < 1e-6
    assert abs(scores[1]) < 1e-6
    assert abs(scores[2] + 1.0) < 1e-6


def test_build_entry_text_concats_title_and_content():
    from app.services.embeddings import build_entry_text
    e = SimpleNamespace(title="Regenbogen-Traum", content="Ich träumte.")
    assert build_entry_text(e) == "Regenbogen-Traum\n\nIch träumte."


def test_build_entry_text_truncates():
    from app.services.embeddings import MAX_EMBED_CHARS, build_entry_text
    e = SimpleNamespace(title="t", content="x" * (MAX_EMBED_CHARS * 2))
    assert len(build_entry_text(e)) <= MAX_EMBED_CHARS


def test_embed_text_returns_vector_and_model():
    from app.services.embeddings import embed_text
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}], "model": "text-embedding-3-small"},
        ))
        vec, model = embed_text("hi")
    assert vec.dtype == np.float32
    assert vec.shape == (3,)
    assert model == "text-embedding-3-small"


def test_embed_text_maps_401_to_502_with_auth_message():
    from app.services.embeddings import embed_text
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(401, json={"error": "bad key"}))
        with pytest.raises(HTTPException) as ei:
            embed_text("x")
    assert ei.value.status_code == 502
    assert "401" in ei.value.detail or "auth" in ei.value.detail.lower()


def test_embed_text_maps_404_to_502_with_model_message():
    from app.services.embeddings import embed_text
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(404, json={"error": "model not found"}))
        with pytest.raises(HTTPException) as ei:
            embed_text("x")
    assert ei.value.status_code == 502
    assert "404" in ei.value.detail or "nicht gefunden" in ei.value.detail.lower()


def test_embed_text_maps_5xx_to_502():
    from app.services.embeddings import embed_text
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(503))
        with pytest.raises(HTTPException) as ei:
            embed_text("x")
    assert ei.value.status_code == 502


def test_embed_text_maps_connect_error_to_502():
    from app.services.embeddings import embed_text
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(HTTPException) as ei:
            embed_text("x")
    assert ei.value.status_code == 502
    assert "unreachable" in ei.value.detail.lower() or "nicht erreichbar" in ei.value.detail.lower()
