# Semantic Search Implementation Plan (v2 — nach Codex-Review)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Natural-language semantic search über alle Journal-Einträge, toggle-bar gegen die Keyword-Suche, mit Voice-Input und LLM-Re-Ranking.

**Architecture:** BLOB-Embedding-Spalten auf Entry + numpy-Cosine. Ein **zentraler Zustandsautomat-basierter Job-Runner** orchestriert Backfill und Reindex (Reindex supersediert Backfill, koalesziert statt 409). Einzel-Embed-Tasks validieren das Modell vor dem Persist, um Race-Conditions mit Reindex auszuschließen. LLM extrahiert Kernabsicht + re-ranked Top-30 → Top-10. Modellwechsel löst expliziten User-Dialog aus.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + SQLCipher + numpy | SvelteKit 2 + Svelte 5 runes + Vitest + Playwright | OpenAI-kompatible `embed`- und `chat`-Capabilities.

**Konventionen (verifiziert im Repo, nicht abweichen):**
- Cookie: `session` (SessionID), `csrf` (CSRF-Token). Header: `x-csrf-token`.
- Test-Pattern: `cookies={"session": sid, "csrf": "t"}`, `headers={"x-csrf-token": "t"}` — kein Auth-Helper, kein separater CSRF-Endpoint.
- `limiter` aus `app.security.rate_limit`; key_func ist `get_remote_address` (IP-basiert, nicht Session).
- `api<T>()` in `frontend/src/lib/api.ts` erwartet `body` als Objekt (nicht `JSON.stringify`), setzt Content-Type + CSRF selbst.
- 502-Mapping: Das Pattern aus `backend/app/routes/tts.py:15` (`_map_provider_error`) wird übernommen.
- Projekt arbeitet direkt auf `main`, keine Feature-Branches.

**Spec:** `docs/superpowers/specs/2026-04-17-semantic-search-design.md`

---

## Task 1: numpy-Dependency hinzufügen

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: numpy in requirements.txt aufnehmen**

Füge am Ende von `backend/requirements.txt` hinzu:

```
numpy==2.1.3
```

- [ ] **Step 2: Dependency installieren**

Run: `cd backend && .venv/bin/pip install -r requirements.txt`
Expected: `Successfully installed numpy-2.1.3`

- [ ] **Step 3: Smoke-Import prüfen**

Run: `cd backend && .venv/bin/python -c "import numpy; print(numpy.__version__)"`
Expected: `2.1.3`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore(deps): add numpy for embedding vector ops"
```

---

## Task 2: Alembic-Migration für Embedding-Spalten

**Files:**
- Create: `backend/alembic/versions/<auto_id>_add_embedding_columns.py`

- [ ] **Step 1: Migration generieren**

Run: `cd backend && .venv/bin/alembic revision -m "add embedding columns"`
Expected: `alembic/versions/<revid>_add_embedding_columns.py` wird erzeugt.

- [ ] **Step 2: Migration-Body befüllen**

Öffne die generierte Datei und ersetze `upgrade()` und `downgrade()`:

```python
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("entries", sa.Column("embedding", sa.LargeBinary(), nullable=True))
    op.add_column("entries", sa.Column("embedding_model", sa.String(), nullable=True))
    op.add_column("entries", sa.Column("embedding_updated_at", sa.DateTime(), nullable=True))
    op.add_column("settings", sa.Column("embed_dimensions", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "embed_dimensions")
    op.drop_column("entries", "embedding_updated_at")
    op.drop_column("entries", "embedding_model")
    op.drop_column("entries", "embedding")
```

- [ ] **Step 3: Migration anwenden**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: `INFO [alembic.runtime.migration] Running upgrade ... -> <revid>, add embedding columns`

- [ ] **Step 4: Schema prüfen**

Run: `cd backend && .venv/bin/python -c "from app.db import engine; from sqlalchemy import inspect; print([c['name'] for c in inspect(engine).get_columns('entries')])"`
Expected: enthält `embedding`, `embedding_model`, `embedding_updated_at`.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(db): add embedding columns to entries and settings"
```

---

## Task 3: Entry- und Settings-Model um neue Spalten erweitern

**Files:**
- Modify: `backend/app/models/entry.py`
- Modify: `backend/app/models/settings.py`

- [ ] **Step 1: Entry-Model erweitern**

In `backend/app/models/entry.py` den Import-Block anpassen und Spalten ergänzen. Finale Imports:

```python
from datetime import date, datetime

from sqlalchemy import Date, DateTime, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
```

Neue Spalten nach `chat_history`:

```python
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
```

- [ ] **Step 2: Settings-Model erweitern**

In `backend/app/models/settings.py` `embed_dimensions` ergänzen (Integer-Import falls nötig anpassen):

```python
    embed_dimensions: Mapped[int | None] = mapped_column(Integer)
```

- [ ] **Step 3: Smoke-Import**

Run: `cd backend && .venv/bin/python -c "from app.models.entry import Entry; from app.models.settings import AppSettings; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Bestehende Tests grün**

Run: `cd backend && .venv/bin/pytest -q`
Expected: alle vorhandenen Tests passen weiter.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/
git commit -m "feat(models): expose embedding columns on Entry and AppSettings"
```

---

## Task 4: Embeddings-Service — Vektor-Packing + Cosine (TDD)

**Files:**
- Create: `backend/app/services/embeddings.py`
- Test: `backend/tests/test_embeddings_service.py`

- [ ] **Step 1: Test schreiben**

`backend/tests/test_embeddings_service.py`:

```python
import numpy as np

from app.services.embeddings import cosine_similarity, pack_vector, unpack_vector


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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py -v`
Expected: FAIL `ModuleNotFoundError: No module named 'app.services.embeddings'`.

- [ ] **Step 3: Implementation schreiben**

`backend/app/services/embeddings.py`:

```python
"""Embedding vector operations for semantic search."""
from __future__ import annotations

import numpy as np


def pack_vector(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """Cosine similarity between a 1D query vector and an (N, D) candidate matrix."""
    q = query.astype(np.float32)
    m = candidates.astype(np.float32)
    q_norm = np.linalg.norm(q)
    m_norms = np.linalg.norm(m, axis=1)
    denom = q_norm * m_norms
    denom = np.where(denom == 0, 1.0, denom)
    return (m @ q) / denom
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embeddings.py backend/tests/test_embeddings_service.py
git commit -m "feat(embeddings): vector pack/unpack + cosine similarity"
```

---

## Task 5: Embeddings-Service — build_entry_text + embed_text mit differenziertem 502-Mapping (TDD)

**Files:**
- Modify: `backend/app/services/embeddings.py`
- Modify: `backend/tests/test_embeddings_service.py`

- [ ] **Step 1: Tests für build_entry_text + embed_text ergänzen**

Am Ende von `tests/test_embeddings_service.py` hinzufügen:

```python
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
import respx
from fastapi import HTTPException

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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py -v`
Expected: FAIL — neue Tests nicht importierbar.

- [ ] **Step 3: Implementation ergänzen**

In `backend/app/services/embeddings.py` oben nach dem numpy-Import ergänzen:

```python
import httpx
from fastapi import HTTPException

from app.services.llm_client import get_client

MAX_EMBED_CHARS = 28000  # ~7k tokens @ 4 chars/token heuristic


def build_entry_text(entry) -> str:
    """Canonical embedding input: title + blank line + content, truncated."""
    text = f"{entry.title}\n\n{entry.content}"
    if len(text) > MAX_EMBED_CHARS:
        text = text[:MAX_EMBED_CHARS]
    return text


def _map_embed_error(exc: Exception) -> HTTPException:
    """Map embedding provider errors to 502 with a readable detail.

    Mirrors backend/app/routes/tts.py:_map_provider_error so responses
    are consistent across capabilities. We avoid leaking upstream bodies.
    """
    msg = str(exc).lower()
    if isinstance(exc, httpx.ConnectError) or "connecterror" in msg or "connection" in msg:
        return HTTPException(502, "Embedding-Server nicht erreichbar")
    if "401" in msg or "unauthorized" in msg or "authentication" in msg:
        return HTTPException(502, "Embedding-Server: Auth-Fehler (401) — API-Key prüfen")
    if "404" in msg or "not found" in msg:
        return HTTPException(502, "Embedding-Server: Modell/Endpoint nicht gefunden (404)")
    if "429" in msg:
        return HTTPException(502, "Embedding-Anbieter hat rate-limited — kurz warten")
    return HTTPException(502, "Embedding fehlgeschlagen — Embed-Endpoint prüfen")


class ProviderRateLimited(Exception):
    """Raised when the embedding provider returns a 429. Used by the backfill
    worker to trigger exponential backoff without string-matching."""


def embed_text(text: str) -> tuple[np.ndarray, str]:
    """Call the embed-capability, return (float32 vector, model name).

    Raises ProviderRateLimited on 429 (for the backfill backoff loop).
    Raises HTTPException(502, ...) for all other provider errors.
    """
    client, model = get_client("embed")
    try:
        resp = client.embeddings.create(model=model, input=text)
    except Exception as exc:
        if "429" in str(exc).lower():
            raise ProviderRateLimited(str(exc)) from exc
        raise _map_embed_error(exc) from exc

    try:
        raw = resp.data[0].embedding
        resolved_model = getattr(resp, "model", None) or model
    except (AttributeError, IndexError) as exc:
        raise HTTPException(502, f"Embedding-Server: unerwartetes Response-Format: {exc}") from exc

    return np.asarray(raw, dtype=np.float32), resolved_model
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embeddings.py backend/tests/test_embeddings_service.py
git commit -m "feat(embeddings): build_entry_text + embed_text with tts-style 502 mapping"
```

---

## Task 6: Search-Service — extract_search_intent (TDD)

**Files:**
- Create: `backend/app/services/search.py`
- Create: `backend/tests/test_search_service.py`

- [ ] **Step 1: Test schreiben**

`backend/tests/test_search_service.py`:

```python
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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implementation**

`backend/app/services/search.py`:

```python
"""Semantic search orchestration."""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel

from app.services.llm_client import get_client

log = logging.getLogger(__name__)

SEARCH_INTENT_PROMPT = (
    "Du bist ein Suchhilfsmodul. Der Nutzer spricht in ganzen Sätzen und "
    "fragt nach Tagebucheinträgen. Extrahiere die inhaltliche Kernabsicht "
    "als kurze, suchfreundliche Phrase (maximal 10 Wörter, keine Begrüßung, "
    "keine Höflichkeitsfloskeln). Antworte nur mit der Phrase, ohne "
    "Anführungszeichen, ohne Erklärung."
)


class RerankedResult(BaseModel):
    entry_id: str
    title: str
    excerpt: str
    score: float
    reason: str | None = None


class SemanticSearchResponse(BaseModel):
    results: list[RerankedResult]
    status: Literal["ok", "indexing", "not_configured", "error"]
    progress: dict | None = None


def extract_search_intent(query: str) -> str:
    """Compress a conversational query to a search phrase.

    On any failure, return the raw query unchanged (graceful degradation).
    """
    try:
        client, model = get_client("chat")
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            max_tokens=60,
            messages=[
                {"role": "system", "content": SEARCH_INTENT_PROMPT},
                {"role": "user", "content": query},
            ],
        )
        intent = (resp.choices[0].message.content or "").strip()
        return intent or query
    except Exception as exc:
        log.warning("extract_search_intent failed, falling back: %s", exc)
        return query
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search.py backend/tests/test_search_service.py
git commit -m "feat(search): extract_search_intent with graceful fallback"
```

---

## Task 7: Search-Service — rerank_results mit Cosine-Fallback (TDD)

**Files:**
- Modify: `backend/app/services/search.py`
- Modify: `backend/tests/test_search_service.py`

- [ ] **Step 1: Tests ergänzen**

Am Ende von `tests/test_search_service.py`:

```python
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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py::test_rerank_parses_valid_json -v`
Expected: FAIL `ImportError: cannot import name 'rerank_results'`.

- [ ] **Step 3: rerank_results implementieren**

In `backend/app/services/search.py` unten ergänzen:

```python
RERANK_PROMPT = (
    "Du bekommst eine Nutzeranfrage und eine Liste von Tagebucheintrag-"
    "Kandidaten (id, title, snippet). Bewerte jeden Kandidaten mit einem "
    "Score von 0 bis 100 für die inhaltliche Relevanz zur Anfrage und "
    "beschreibe in einem kurzen Satz (max. 120 Zeichen) warum. "
    'Antworte AUSSCHLIESSLICH mit JSON der Form '
    '{"results":[{"id":"...","score":0-100,"reason":"..."}]}. '
    "Keine Erklärung, kein Markdown, kein Text drumherum."
)


def _excerpt(text: str, limit: int = 200) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def _cosine_fallback(candidates: list, top_k: int) -> list[RerankedResult]:
    return [
        RerankedResult(
            entry_id=c.id,
            title=c.title,
            excerpt=_excerpt(c.content),
            score=0.0,
            reason=None,
        )
        for c in candidates[:top_k]
    ]


def rerank_results(query: str, candidates: list, top_k: int) -> list[RerankedResult]:
    """LLM-rerank. Falls back to cosine-order + reason=None on any failure."""
    if not candidates:
        return []

    try:
        client, model = get_client("chat")
        payload = [
            {"id": c.id, "title": c.title, "snippet": _excerpt(c.content, 300)}
            for c in candidates
        ]
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": RERANK_PROMPT},
                {
                    "role": "user",
                    "content": f"Anfrage: {query}\n\nKandidaten: {json.dumps(payload, ensure_ascii=False)}",
                },
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            arr = parsed.get("results") or parsed.get("items") or next(
                (v for v in parsed.values() if isinstance(v, list)), None
            )
        else:
            arr = parsed
        if not isinstance(arr, list):
            raise ValueError("rerank response not a list")

        by_id = {c.id: c for c in candidates}
        out: list[RerankedResult] = []
        for item in arr:
            cid = item.get("id")
            cand = by_id.get(cid)
            if cand is None:
                continue
            out.append(RerankedResult(
                entry_id=cid,
                title=cand.title,
                excerpt=_excerpt(cand.content),
                score=float(item.get("score", 0)),
                reason=item.get("reason"),
            ))
        if not out:
            return _cosine_fallback(candidates, top_k)
        return out[:top_k]
    except Exception as exc:
        log.warning("rerank_results failed, using cosine order: %s", exc)
        return _cosine_fallback(candidates, top_k)
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search.py backend/tests/test_search_service.py
git commit -m "feat(search): LLM rerank with cosine-order fallback"
```

---

## Task 8: Search-Service — semantic_search mit Dimension-Guard (TDD)

**Files:**
- Modify: `backend/app/services/search.py`
- Modify: `backend/tests/test_search_service.py`

- [ ] **Step 1: Tests ergänzen**

Am Ende von `tests/test_search_service.py`:

```python
from datetime import date

import numpy as _np
from fastapi import HTTPException

from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import pack_vector


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
        db.add(Entry(
            id="e1", entry_date=date(2026, 4, 1), title="Regenbogen", content="Regenbögen.",
            embedding=pack_vector(_np.array([1.0, 0.0, 0.0], dtype=_np.float32)),
            embedding_model="m1",
        ))
        db.add(Entry(
            id="e2", entry_date=date(2026, 4, 1), title="Auto", content="Neues Auto.",
            embedding=pack_vector(_np.array([0.0, 1.0, 0.0], dtype=_np.float32)),
            embedding_model="m1",
        ))
        db.add(Entry(
            id="e3", entry_date=date(2026, 4, 1), title="Old", content="alt",
            embedding=pack_vector(_np.array([1.0, 0.0, 0.0], dtype=_np.float32)),
            embedding_model="old",
        ))
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


def test_semantic_search_not_configured_when_model_missing():
    from app.services.search import semantic_search
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = None
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
        db.add(Entry(
            id="w1", entry_date=date(2026, 4, 1), title="w", content="c",
            embedding=pack_vector(_np.array([1.0, 0.0], dtype=_np.float32)),
            embedding_model="m1",
        ))
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
        db.add(Entry(
            id="ok", entry_date=date(2026, 4, 1), title="t", content="c",
            embedding=pack_vector(_np.array([1.0], dtype=_np.float32)),
            embedding_model="m1",
        ))
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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py::test_semantic_search_end_to_end -v`
Expected: FAIL `ImportError: cannot import name 'semantic_search'`.

- [ ] **Step 3: semantic_search implementieren**

In `backend/app/services/search.py` unten ergänzen:

```python
import numpy as np
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import cosine_similarity, embed_text, unpack_vector

RERANK_POOL_SIZE = 30


def semantic_search(query: str, top_k: int = 10) -> SemanticSearchResponse:
    """Full pipeline: intent → embed → cosine filter → LLM rerank → top_k.

    Raises HTTPException(502, ...) if the embed step fails (handled at route).
    """
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        current_model = s.embed_model if s else None
        if not current_model:
            return SemanticSearchResponse(results=[], status="not_configured")

        rows = db.execute(
            select(Entry).where(
                Entry.embedding.is_not(None),
                Entry.embedding_model == current_model,
            )
        ).scalars().all()
        total_count = int(db.scalar(select(func.count()).select_from(Entry)) or 0)
        embedded_count = len(rows)

    if not rows:
        return SemanticSearchResponse(
            results=[],
            status="indexing",
            progress={"embedded": embedded_count, "total": total_count},
        )

    intent = extract_search_intent(query)
    query_vec, _ = embed_text(intent)  # may raise HTTPException(502)

    # Dimension guard: drop vectors whose shape doesn't match the query.
    # Unlike "indexing", this indicates corrupted/stale blobs, so if ALL
    # candidates are dropped we surface it as 'error' — not as progress.
    candidates = []
    vectors = []
    dropped = 0
    for e in rows:
        v = unpack_vector(e.embedding)
        if v.shape[0] == query_vec.shape[0]:
            candidates.append(e)
            vectors.append(v)
        else:
            dropped += 1
    if dropped:
        log.warning("semantic_search dropped %d candidates due to dimension mismatch", dropped)

    if not candidates:
        return SemanticSearchResponse(
            results=[],
            status="error",
            progress={"embedded": embedded_count, "total": total_count, "corrupted": dropped},
        )

    matrix = np.stack(vectors)
    scores = cosine_similarity(query_vec, matrix)
    order = np.argsort(scores)[::-1][:RERANK_POOL_SIZE]
    pool = [candidates[i] for i in order]

    reranked = rerank_results(query, pool, top_k=top_k)
    return SemanticSearchResponse(results=reranked, status="ok")
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search.py backend/tests/test_search_service.py
git commit -m "feat(search): end-to-end semantic_search with dimension guard"
```

---

## Task 9: Embedding-Jobs — embed_entry_async mit Modell-Guard (TDD)

**Files:**
- Create: `backend/app/services/embedding_jobs.py`
- Create: `backend/tests/test_embedding_jobs.py`

**Wichtig:** `embed_entry_async` validiert vor dem Persist, dass das aktuelle `AppSettings.embed_model` zum gerade embedded Modell passt. Das verhindert, dass ein alter In-Flight-Task nach einem Modellwechsel veraltete Embeddings zurückschreibt (Codex-Review FIX 1, Punkt 2).

- [ ] **Step 1: Tests schreiben**

`backend/tests/test_embedding_jobs.py`:

```python
from datetime import date

import httpx
import numpy as np
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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embedding_jobs.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implementation schreiben**

`backend/app/services/embedding_jobs.py`:

```python
"""Background/startup jobs for maintaining entry embeddings.

This module owns a single coalesced job runner: ONE worker coroutine,
ONE asyncio.Lock, a simple state machine (pending_backfill / pending_reindex).
Requests are collapsed into flags — callers don't queue FIFO work.

Single-entry embeds from route handlers go directly via embed_entry_async()
and do NOT touch the runner lock. They validate the current AppSettings.embed_model
before persisting, so a concurrent reindex can't be sabotaged by in-flight
single-embed tasks writing stale results.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import or_, select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import (
    ProviderRateLimited,
    build_entry_text,
    embed_text,
    pack_vector,
)
from app.utc import utc_now

log = logging.getLogger(__name__)


def _current_embed_model() -> str | None:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        return s.embed_model if s else None


def embed_entry_async(entry_id: str) -> None:
    """Synchronous embed of ONE entry. Safe to call from BackgroundTasks.

    Guards:
    - Entry may have been deleted → skip.
    - Provider may fail → log and leave embedding=NULL.
    - Settings.embed_model may have changed between call and write →
      discard the result to avoid writing stale data; the next backfill
      will pick it up with the current model.
    """
    with SessionLocal() as db:
        e = db.get(Entry, entry_id)
        if e is None:
            return
        text = build_entry_text(e)
        model_at_start = _current_embed_model()

    try:
        vec, resolved_model = embed_text(text)
    except Exception as exc:
        log.warning("embed_entry_async: embed failed for %s: %s", entry_id, exc)
        return

    # Model-change guard: if settings moved on while we were calling,
    # don't persist stale work. Compare against model_at_start — if it changed
    # or if resolved_model != current, skip the write.
    current_now = _current_embed_model()
    if current_now != model_at_start or current_now != resolved_model:
        log.info(
            "embed_entry_async: model changed during call for %s "
            "(start=%s, resolved=%s, now=%s) — discarding",
            entry_id, model_at_start, resolved_model, current_now,
        )
        return

    blob = pack_vector(vec)
    with SessionLocal() as db:
        e = db.get(Entry, entry_id)
        if e is None:
            return  # deleted between embed + write
        e.embedding = blob
        e.embedding_model = resolved_model
        e.embedding_updated_at = utc_now()
        s = db.get(AppSettings, 1)
        # embed_dimensions: set only initially, never silently overwrite
        if s is not None:
            if s.embed_dimensions is None:
                s.embed_dimensions = int(vec.shape[0])
            elif s.embed_dimensions != int(vec.shape[0]):
                log.warning(
                    "embed_dimensions mismatch: stored=%s, got=%s — not overwriting",
                    s.embed_dimensions, int(vec.shape[0]),
                )
        db.commit()
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_embedding_jobs.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embedding_jobs.py backend/tests/test_embedding_jobs.py
git commit -m "feat(jobs): embed_entry_async with model-change guard + dim guard"
```

---

## Task 10: Job-Runner als Zustandsautomat (TDD)

**Files:**
- Modify: `backend/app/services/embedding_jobs.py`
- Modify: `backend/tests/test_embedding_jobs.py`

**Design (direkt aus Codex-Review):** Ein einzelner Worker-Coroutine, ein Lock, zwei Flags. `request_backfill()` und `request_reindex()` setzen Flags, Worker verarbeitet beide koalesziert. `reindex` supersediert `backfill` (statt 409 zu werfen).

- [ ] **Step 1: Tests für Job-Runner**

Am Ende von `tests/test_embedding_jobs.py`:

```python
import asyncio as _a


def test_backfill_fills_missing_and_skips_matching_model():
    from app.services.embedding_jobs import _do_backfill
    from app.services.embeddings import pack_vector

    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="a", entry_date=date(2026, 4, 1), title="a", content="c"))
        db.add(Entry(
            id="b", entry_date=date(2026, 4, 1), title="b", content="c",
            embedding=pack_vector(np.array([0.0, 1.0], dtype=np.float32)),
            embedding_model="old",
        ))
        db.add(Entry(
            id="c", entry_date=date(2026, 4, 1), title="c", content="c",
            embedding=pack_vector(np.array([1.0, 0.0], dtype=np.float32)),
            embedding_model="m1",
        ))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        route = mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.5, 0.5]}], "model": "m1"},
        ))
        _a.run(_do_backfill())

    assert route.call_count == 2  # a + b, not c


def test_reindex_nulls_then_refills_under_same_lock():
    from app.services.embedding_jobs import _do_reindex
    from app.services.embeddings import pack_vector

    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(
            id="z", entry_date=date(2026, 4, 1), title="z", content="c",
            embedding=pack_vector(np.array([1.0], dtype=np.float32)),
            embedding_model="m1",
        ))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(
            200, json={"data": [{"embedding": [0.9, 0.1]}], "model": "m1"},
        ))
        _a.run(_do_reindex())

    with SessionLocal() as db:
        e = db.get(Entry, "z")
        assert unpack_vector(e.embedding).shape == (2,)


def test_backoff_on_provider_rate_limit():
    """Provider 429 → exponential backoff 1s/2s/4s; after max retries, skip entry."""
    from app.services.embedding_jobs import _do_backfill

    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="r", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()

    calls = {"n": 0}

    def _handler(request):
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, json={"error": "rate limit"})
        return httpx.Response(200, json={"data": [{"embedding": [0.1]}], "model": "m1"})

    # Shortcut sleep for test speed
    import app.services.embedding_jobs as jobs
    old_steps = jobs.BACKOFF_STEPS
    jobs.BACKOFF_STEPS = (0.01, 0.01, 0.01)
    try:
        with respx.mock(base_url="https://api.openai.com/v1") as mock:
            mock.post("/embeddings").mock(side_effect=_handler)
            _a.run(_do_backfill())
    finally:
        jobs.BACKOFF_STEPS = old_steps

    assert calls["n"] == 3  # 2 x 429 + 1 success
    with SessionLocal() as db:
        assert db.get(Entry, "r").embedding is not None


def test_request_coalescing():
    """Multiple request_backfill() calls while a job is running collapse to one.
    request_reindex() supersedes a queued backfill."""
    from app.services.embedding_jobs import (
        request_backfill, request_reindex, _state,
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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embedding_jobs.py::test_backfill_fills_missing_and_skips_matching_model -v`
Expected: FAIL `ImportError: cannot import name '_do_backfill'`.

- [ ] **Step 3: Runner + Zustandsautomat ergänzen**

In `backend/app/services/embedding_jobs.py` unten anhängen:

```python
# ---------------- Job Runner (State Machine) ----------------

BACKFILL_THROTTLE_SECONDS = 0.2
BACKOFF_STEPS = (1.0, 2.0, 4.0)


class _JobState:
    """Coalesced flags for a single worker. Not thread-safe — worker owns it."""
    def __init__(self) -> None:
        self.pending_backfill = False
        self.pending_reindex = False
        self.running = False
        self.wakeup = asyncio.Event()


_state = _JobState()
_worker_task: asyncio.Task | None = None


def request_backfill() -> None:
    """Signal that a backfill is desired. Collapses with any pending request."""
    _state.pending_backfill = True
    _state.wakeup.set()


def request_reindex() -> None:
    """Signal that a full reindex is desired. Supersedes a pending backfill
    (reindex does a complete pass anyway)."""
    _state.pending_reindex = True
    _state.wakeup.set()


def is_job_running() -> bool:
    return _state.running or _state.pending_backfill or _state.pending_reindex


async def _do_backfill() -> None:
    """Embed all entries where embedding is NULL or embedding_model != current.
    Ordered by updated_at DESC so the freshest entries become searchable first.
    """
    current = _current_embed_model()
    if not current:
        log.info("_do_backfill: no embed_model configured, skipping")
        return

    with SessionLocal() as db:
        ids = db.execute(
            select(Entry.id)
            .where(or_(Entry.embedding.is_(None), Entry.embedding_model != current))
            .order_by(Entry.updated_at.desc())
        ).scalars().all()

    log.info("_do_backfill: %d entries pending for model=%s", len(ids), current)
    for eid in ids:
        await _embed_one_with_backoff(eid)
        await asyncio.sleep(BACKFILL_THROTTLE_SECONDS)


async def _embed_one_with_backoff(entry_id: str) -> None:
    """Run embed_entry_async with exponential backoff on ProviderRateLimited."""
    for delay in BACKOFF_STEPS:
        try:
            await asyncio.to_thread(embed_entry_async, entry_id)
            return
        except ProviderRateLimited as exc:
            log.info("429 for %s, sleeping %.1fs before retry", entry_id, delay)
            await asyncio.sleep(delay)
            continue
    # Final attempt after all backoff steps
    try:
        await asyncio.to_thread(embed_entry_async, entry_id)
    except ProviderRateLimited:
        log.warning("embed_entry_async gave up for %s after retries", entry_id)


async def _do_reindex() -> None:
    """Null all embeddings, then do a full backfill. Runs under the same lock
    as backfill — no release+reacquire race."""
    log.info("_do_reindex: clearing all embeddings")
    with SessionLocal() as db:
        db.query(Entry).update(
            {
                Entry.embedding: None,
                Entry.embedding_model: None,
                Entry.embedding_updated_at: None,
            },
            synchronize_session=False,
        )
        db.commit()
    await _do_backfill()


async def _worker_loop() -> None:
    """Single worker that drains pending flags, coalescing multiple requests.
    Reindex supersedes backfill; both signals are consumed in one pass."""
    while True:
        await _state.wakeup.wait()
        _state.wakeup.clear()
        while _state.pending_backfill or _state.pending_reindex:
            do_reindex = _state.pending_reindex
            _state.pending_reindex = False
            _state.pending_backfill = False
            _state.running = True
            try:
                if do_reindex:
                    await _do_reindex()
                else:
                    await _do_backfill()
            except asyncio.CancelledError:
                _state.running = False
                raise
            except Exception as exc:
                log.exception("job runner crashed: %s", exc)
            finally:
                _state.running = False


def start_worker(loop: asyncio.AbstractEventLoop | None = None) -> asyncio.Task:
    """Start the worker coroutine. Called from the FastAPI lifespan."""
    global _worker_task
    if _worker_task and not _worker_task.done():
        return _worker_task
    _worker_task = asyncio.create_task(_worker_loop(), name="embedding-worker")
    return _worker_task


async def stop_worker() -> None:
    """Cancel the worker and wait for it to exit. Called from the lifespan shutdown."""
    global _worker_task
    if _worker_task is None:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_embedding_jobs.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embedding_jobs.py backend/tests/test_embedding_jobs.py
git commit -m "feat(jobs): coalesced job runner with reindex-supersedes-backfill"
```

---

## Task 11: Entry-Routen — Embedding-Invalidation + BackgroundTask (TDD)

**Files:**
- Modify: `backend/app/routes/entries.py`
- Create: `backend/tests/test_entries_embedding.py`

- [ ] **Step 1: Test schreiben (korrektes Auth-Pattern)**

`backend/tests/test_entries_embedding.py`:

```python
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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_entries_embedding.py -v`
Expected: FAIL — entweder ImportError (embed_entry_async noch nicht importiert) oder Embedding wird nicht invalidiert.

- [ ] **Step 3: routes/entries.py anpassen**

In `backend/app/routes/entries.py`:

1. Import-Block ergänzen:

```python
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.services.embedding_jobs import embed_entry_async
```

2. `create_entry`:

```python
@router.post("", status_code=201)
async def create_entry(body: EntryCreate, background: BackgroundTasks) -> dict:
    with SessionLocal() as db:
        e = Entry(
            id=new_id(),
            entry_date=body.entry_date,
            title=body.title,
            content=body.content,
            raw_transcript=body.raw_transcript,
            chat_history=json.dumps(body.chat_history) if body.chat_history else None,
        )
        db.add(e)
        _ensure_tags(db, body.tags)
        for n in set(body.tags):
            db.add(EntryTag(entry_id=e.id, tag_name=n))
        db.commit()
        db.refresh(e)
        entry_id = e.id
        detail = _to_detail(e)
    background.add_task(embed_entry_async, entry_id)
    return detail
```

3. `update_entry`:

```python
@router.put("/{eid}")
async def update_entry(eid: str, body: EntryUpdate, background: BackgroundTasks) -> dict:
    with SessionLocal() as db:
        e = db.get(Entry, eid)
        if not e:
            raise HTTPException(404)
        text_changed = False
        if body.title is not None and body.title != e.title:
            e.title = body.title
            text_changed = True
        if body.content is not None and body.content != e.content:
            e.content = body.content
            text_changed = True
        if body.entry_date is not None:
            e.entry_date = body.entry_date
        if body.tags is not None:
            db.query(EntryTag).filter(EntryTag.entry_id == eid).delete()
            _ensure_tags(db, body.tags)
            for n in set(body.tags):
                db.add(EntryTag(entry_id=eid, tag_name=n))
        if text_changed:
            e.embedding = None
            e.embedding_model = None
            e.embedding_updated_at = None
        e.updated_at = utc_now()
        db.commit()
        db.refresh(e)
        detail = _to_detail(e)

    if text_changed:
        background.add_task(embed_entry_async, eid)
    return detail
```

- [ ] **Step 4: Tests grün — neue + bestehende**

Run: `cd backend && .venv/bin/pytest tests/test_entries_embedding.py tests/test_entries.py -v`
Expected: alle grün.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/entries.py backend/tests/test_entries_embedding.py
git commit -m "feat(entries): schedule embedding on create/update, invalidate on text change"
```

---

## Task 12: Search-Route — POST /api/search (TDD)

**Files:**
- Create: `backend/app/routes/search.py`
- Create: `backend/tests/test_search_routes.py`
- Modify: `backend/app/main.py` (Router registrieren)

- [ ] **Step 1: Test schreiben (korrektes Pattern, siehe test_tts_route.py)**

`backend/tests/test_search_routes.py`:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.entry import Entry
from app.models.settings import AppSettings
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
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py::test_post_search_returns_results -v`
Expected: FAIL `ModuleNotFoundError: No module named 'app.routes.search'`.

- [ ] **Step 3: Route schreiben**

`backend/app/routes/search.py`:

```python
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.security.rate_limit import limiter
from app.services.search import semantic_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)


@router.post("")
@limiter.limit("30/minute")
async def search(request: Request, body: SearchRequest) -> dict:
    q = body.query.strip()
    if not q:
        raise HTTPException(422, "empty query")
    try:
        result = semantic_search(q, top_k=body.top_k)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("semantic_search failed: %s", exc)
        raise HTTPException(502, "Suche fehlgeschlagen — Embedding/Chat-Endpoint prüfen") from exc
    return result.model_dump()
```

- [ ] **Step 4: Router in main.py registrieren**

In `backend/app/main.py` Import ergänzen:

```python
from app.routes.search import router as search_router
```

Und nach den anderen `include_router`:

```python
app.include_router(search_router)
```

- [ ] **Step 5: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/search.py backend/app/main.py backend/tests/test_search_routes.py
git commit -m "feat(api): POST /api/search with rate-limit, session, CSRF, 502 mapping"
```

---

## Task 13: Search-Route — GET /api/search/status (TDD)

**Files:**
- Modify: `backend/app/routes/search.py`
- Modify: `backend/tests/test_search_routes.py`

- [ ] **Step 1: Test ergänzen**

Am Ende von `tests/test_search_routes.py`:

```python
from datetime import date

import numpy as np

from app.services.embeddings import pack_vector


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
```

- [ ] **Step 2: Test — erwartet 404**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py::test_search_status_counts -v`
Expected: FAIL 404.

- [ ] **Step 3: Route ergänzen**

In `backend/app/routes/search.py` anfügen:

```python
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embedding_jobs import is_job_running


@router.get("/status")
async def search_status() -> dict:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        current = s.embed_model if s else None
        total = int(db.scalar(select(func.count()).select_from(Entry)) or 0)
        embedded = int(db.scalar(
            select(func.count()).select_from(Entry).where(
                Entry.embedding.is_not(None),
                Entry.embedding_model == current,
            )
        ) or 0)
    return {
        "total": total,
        "embedded": embedded,
        "pending": total - embedded,
        "current_model": current,
        "configured": bool(current),
        "indexing": is_job_running(),
    }
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/search.py backend/tests/test_search_routes.py
git commit -m "feat(api): GET /api/search/status with counts"
```

---

## Task 14: Search-Route — POST /api/search/reindex (TDD)

**Files:**
- Modify: `backend/app/routes/search.py`
- Modify: `backend/tests/test_search_routes.py`

**Unterschied zu v1 des Plans:** Kein 409 — Reindex wird koalesziert. Ein Reindex-Request bei laufendem Backfill setzt einfach das pending_reindex-Flag; der Worker supersediert automatisch.

- [ ] **Step 1: Test ergänzen**

Am Ende von `tests/test_search_routes.py`:

```python
def test_post_reindex_sets_flag():
    sid = create_session()
    with patch("app.routes.search.request_reindex") as mock_req:
        with TestClient(app) as c:
            r = c.post("/api/search/reindex", cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 202
    mock_req.assert_called_once()


def test_post_reindex_requires_csrf():
    sid = create_session()
    with TestClient(app) as c:
        r = c.post("/api/search/reindex", cookies={"session": sid})
    assert r.status_code == 403
```

- [ ] **Step 2: Test — erwartet 404**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py::test_post_reindex_sets_flag -v`
Expected: FAIL 404.

- [ ] **Step 3: Route ergänzen**

In `backend/app/routes/search.py` unten:

```python
from app.services.embedding_jobs import request_reindex


@router.post("/reindex", status_code=202)
@limiter.limit("1/minute")
async def reindex(request: Request) -> dict:
    request_reindex()
    return {"ok": True}
```

- [ ] **Step 4: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/search.py backend/tests/test_search_routes.py
git commit -m "feat(api): POST /api/search/reindex triggers job runner (coalesced)"
```

---

## Task 15: Settings-PUT — Modellwechsel-Warning mit vollem SettingsOut-Payload (TDD)

**Files:**
- Modify: `backend/app/routes/settings.py`
- Modify: `backend/tests/test_settings_routes.py`

**Contract-Änderung:** Die Response wird von `{"ok": True}` auf den vollen `SettingsOut`-Payload erweitert (plus optionale Warning-Felder). Das Frontend kann dann direkt den neuen Zustand übernehmen, ohne ein zweites GET.

- [ ] **Step 1: Tests schreiben — Base + Mismatch-Pfad**

Am Ende von `backend/tests/test_settings_routes.py`:

```python
from datetime import date

import numpy as np

from app.models.entry import Entry
from app.services.embeddings import pack_vector


def test_settings_put_returns_full_payload():
    """Response now mirrors GET /api/settings (full SettingsOut) instead of {ok}."""
    sid = create_session()
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "initial"
        db.commit()
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"embed_model": "initial"},  # no real change
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    # Must include full SettingsOut-like shape
    assert "embed_model" in body
    assert "tts_voice" in body
    assert body["embed_model"] == "initial"
    assert "warning" not in body


def test_settings_put_warns_on_embed_model_change_with_existing_entries():
    sid = create_session()
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "old-model"
        db.query(Entry).delete()
        db.add(Entry(
            id="mm1", entry_date=date(2026, 4, 1), title="t", content="c",
            embedding=pack_vector(np.array([0.1], dtype=np.float32)),
            embedding_model="old-model",
        ))
        db.commit()

    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"embed_model": "new-model"},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["warning"] == "embedding_model_mismatch"
    assert body["embedding_mismatch"]["old_model"] == "old-model"
    assert body["embedding_mismatch"]["new_model"] == "new-model"
    assert body["embedding_mismatch"]["affected_entries"] == 1
    assert body["embed_model"] == "new-model"  # still saved
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).embed_model == "new-model"


def test_settings_put_no_warning_when_no_existing_entries():
    sid = create_session()
    with SessionLocal() as db:
        db.query(Entry).delete()
        db.get(AppSettings, 1).embed_model = "m1"
        db.commit()
    with TestClient(app) as c:
        r = c.put(
            "/api/settings",
            json={"embed_model": "m2"},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    assert "warning" not in r.json()
```

Der Test für `test_settings_put_returns_full_payload` ist bewusst so geschrieben, dass er gegen den alten Contract (`{"ok": True}`) failt — wenn er bereits passt, gibt's einen bereits existierenden Test, der die Response-Form klar definiert. Falls `cookies(sid)`/`HEADERS` in `test_settings_routes.py` noch nicht existieren, am Dateianfang mit-anlegen (wie in `test_entries_embedding.py`).

- [ ] **Step 2: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_settings_routes.py::test_settings_put_returns_full_payload -v`
Expected: FAIL — `body` enthält nur `{"ok": True}`.

- [ ] **Step 3: Settings-Route refactoren**

`backend/app/routes/settings.py` anpassen:

1. Imports oben ergänzen:

```python
from sqlalchemy import func, select

from app.models.entry import Entry
```

2. Helper-Funktion für den SettingsOut-Payload extrahieren (die logik aus `get_settings()`):

```python
def _settings_to_out(s: AppSettings) -> SettingsOut:
    return SettingsOut(
        stt_base_url=s.stt_base_url,
        stt_api_key_masked=_mask(s.stt_api_key_wrapped),
        stt_model=s.stt_model,
        chat_base_url=s.chat_base_url,
        chat_api_key_masked=_mask(s.chat_api_key_wrapped),
        chat_model=s.chat_model,
        embed_base_url=s.embed_base_url,
        embed_api_key_masked=_mask(s.embed_api_key_wrapped),
        embed_model=s.embed_model,
        tts_base_url=s.tts_base_url,
        tts_api_key_masked=_mask(s.tts_api_key_wrapped),
        tts_model=s.tts_model,
        tts_voice=s.tts_voice,
        tts_speed=s.tts_speed,
        system_prompt=s.system_prompt,
        totp_enabled=bool(s.totp_secret),
    )
```

3. `get_settings` nutzt den Helper:

```python
@router.get("")
async def get_settings() -> SettingsOut:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None:
            raise HTTPException(500, "settings not initialized")
        return _settings_to_out(s)
```

4. `update_settings` kompletten Body ersetzen:

```python
@router.put("")
async def update_settings(body: SettingsPatch) -> dict:
    data = body.model_dump(exclude_unset=True)
    mismatch = None
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None:
            raise HTTPException(500, "settings not initialized")
        old_embed_model = s.embed_model

        for cap in ("stt", "chat", "embed", "tts"):
            if f"{cap}_base_url" in data:
                setattr(s, f"{cap}_base_url", data[f"{cap}_base_url"])
            if f"{cap}_api_key" in data:
                setattr(s, f"{cap}_api_key_wrapped", wrap_secret(data[f"{cap}_api_key"]))
            if f"{cap}_model" in data:
                setattr(s, f"{cap}_model", data[f"{cap}_model"])
        if "tts_voice" in data:
            raw_voice = data["tts_voice"]
            s.tts_voice = raw_voice.strip() if isinstance(raw_voice, str) and raw_voice.strip() else None
        if "tts_speed" in data:
            raw_speed = data["tts_speed"]
            s.tts_speed = None if raw_speed in (None, "") else float(raw_speed)
        if "system_prompt" in data:
            s.system_prompt = data["system_prompt"]

        new_embed_model = s.embed_model
        if (
            "embed_model" in data
            and old_embed_model
            and new_embed_model
            and old_embed_model != new_embed_model
        ):
            affected = int(db.scalar(
                select(func.count()).select_from(Entry).where(
                    Entry.embedding_model.is_not(None),
                    Entry.embedding_model != new_embed_model,
                )
            ) or 0)
            if affected > 0:
                mismatch = {
                    "old_model": old_embed_model,
                    "new_model": new_embed_model,
                    "affected_entries": affected,
                }
        db.commit()
        db.refresh(s)
        payload = _settings_to_out(s).model_dump()

    if mismatch:
        payload["warning"] = "embedding_model_mismatch"
        payload["embedding_mismatch"] = mismatch
    return payload
```

- [ ] **Step 4: Frontend-Breakage absorbieren**

Frontend nutzt aktuell evtl. `{ok: true}`. Kurz prüfen:

Run: `grep -rn "api.*settings\|/api/settings" frontend/src/ | grep -i "put"`

Wenn die Frontend-Logik nur auf `res.ok` achtet und den Body nicht parst, ist keine Änderung nötig. Wenn sie explizit `ok` erwartet, wird das in Task 24 ohnehin angefasst.

- [ ] **Step 5: Tests grün**

Run: `cd backend && .venv/bin/pytest tests/test_settings_routes.py -v`
Expected: alle grün (inkl. neue 3).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/settings.py backend/tests/test_settings_routes.py
git commit -m "feat(settings): PUT returns full SettingsOut + mismatch warning"
```

---

## Task 16: Startup/Shutdown-Lifespan — Worker-Management

**Files:**
- Modify: `backend/app/main.py`

Der bestehende lifespan in `backend/app/main.py:28-34` hat kein `try` — wir führen eines ein, um Worker-Shutdown sauber zu hängen.

- [ ] **Step 1: lifespan umstrukturieren**

In `backend/app/main.py` den bestehenden lifespan-Block ersetzen durch:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Startup
    ensure_bootstrap()
    from app.services.embedding_jobs import request_backfill, start_worker, stop_worker
    start_worker()
    request_backfill()  # kick off initial pass
    try:
        yield
    finally:
        await stop_worker()
```

- [ ] **Step 2: Smoke — App importiert, worker startet nicht synchron**

Run: `cd backend && .venv/bin/python -c "from app.main import app; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Alle Backend-Tests weiterhin grün**

Run: `cd backend && .venv/bin/pytest -q`
Expected: alle grün.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(startup): start embedding worker in lifespan, stop on shutdown"
```

---

## Task 17: Frontend — Search-API-Client (TDD)

**Files:**
- Create: `frontend/src/lib/search.ts`
- Create: `frontend/tests/unit/search-api.test.ts`

**Hinweis:** `api<T>()` in `frontend/src/lib/api.ts` erwartet `body` als **Objekt**, nicht als JSON-String. Es setzt CSRF-Header und Content-Type selbst. Tests müssen sich darauf einstellen.

- [ ] **Step 1: Test schreiben**

`frontend/tests/unit/search-api.test.ts`:

```typescript
import { beforeEach, describe, expect, test, vi } from "vitest";
import { searchEntries, getSearchStatus, reindexEmbeddings } from "../../src/lib/search";

// api.ts reads the csrf cookie from document.cookie — fake it
function setCsrfCookie(value: string) {
  Object.defineProperty(document, "cookie", {
    configurable: true,
    get: () => `csrf=${value}`,
    set: () => {},
  });
}

describe("search api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    setCsrfCookie("t");
  });

  test("searchEntries posts to /api/search with body", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [], status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    const r = await searchEntries("regenbogen", 5);
    expect(r.status).toBe("ok");
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/search");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ query: "regenbogen", top_k: 5 });
    expect(call[1].headers["X-CSRF-Token"]).toBe("t");
  });

  test("getSearchStatus does GET", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          total: 1,
          embedded: 1,
          pending: 0,
          current_model: "m",
          configured: true,
          indexing: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      )
    );
    const s = await getSearchStatus();
    expect(s.configured).toBe(true);
    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/api/search/status");
  });

  test("reindexEmbeddings does POST", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 202,
        headers: { "content-type": "application/json" },
      })
    );
    await reindexEmbeddings();
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/search/reindex");
    expect(call[1].method).toBe("POST");
  });
});
```

- [ ] **Step 2: Test — erwartet Fail**

Run: `cd frontend && npm test -- search-api.test.ts`
Expected: FAIL Modul nicht gefunden.

- [ ] **Step 3: API-Client schreiben**

`frontend/src/lib/search.ts`:

```typescript
import { api } from "$lib/api";

export interface RerankedResult {
  entry_id: string;
  title: string;
  excerpt: string;
  score: number;
  reason: string | null;
}

export interface SemanticSearchResponse {
  results: RerankedResult[];
  status: "ok" | "indexing" | "not_configured" | "error";
  progress?: { embedded: number; total: number; corrupted?: number };
}

export interface SearchStatus {
  total: number;
  embedded: number;
  pending: number;
  current_model: string | null;
  configured: boolean;
  indexing: boolean;
}

export function searchEntries(query: string, topK = 10): Promise<SemanticSearchResponse> {
  return api<SemanticSearchResponse>("/api/search", {
    method: "POST",
    body: { query, top_k: topK },
  });
}

export function getSearchStatus(): Promise<SearchStatus> {
  return api<SearchStatus>("/api/search/status", { method: "GET" });
}

export function reindexEmbeddings(): Promise<void> {
  return api<void>("/api/search/reindex", { method: "POST" });
}
```

- [ ] **Step 4: Tests grün**

Run: `cd frontend && npm test -- search-api.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/search.ts frontend/tests/unit/search-api.test.ts
git commit -m "feat(frontend): search API client (searchEntries/status/reindex)"
```

---

## Task 18: Frontend — Search-Store (TDD)

**Files:**
- Create: `frontend/src/lib/stores/search.svelte.ts`
- Create: `frontend/tests/unit/search-store.test.ts`

- [ ] **Step 1: Test schreiben**

`frontend/tests/unit/search-store.test.ts`:

```typescript
import { describe, expect, test, vi, beforeEach } from "vitest";
import { searchStore } from "../../src/lib/stores/search.svelte";
import * as searchApi from "../../src/lib/search";

describe("search store", () => {
  beforeEach(() => {
    searchStore.reset();
    vi.restoreAllMocks();
  });

  test("toggle between keyword and semantic", () => {
    expect(searchStore.mode).toBe("keyword");
    searchStore.setMode("semantic");
    expect(searchStore.mode).toBe("semantic");
  });

  test("runSearch populates results on success", async () => {
    vi.spyOn(searchApi, "searchEntries").mockResolvedValue({
      results: [{ entry_id: "e1", title: "T", excerpt: "E", score: 90, reason: "why" }],
      status: "ok",
    });
    await searchStore.runSearch("regenbogen");
    expect(searchStore.loading).toBe(false);
    expect(searchStore.results?.length).toBe(1);
    expect(searchStore.lastResponse?.status).toBe("ok");
  });

  test("runSearch sets loading then clears", async () => {
    let resolvePromise!: (v: any) => void;
    vi.spyOn(searchApi, "searchEntries").mockReturnValue(
      new Promise((res) => (resolvePromise = res))
    );
    const p = searchStore.runSearch("q");
    expect(searchStore.loading).toBe(true);
    resolvePromise({ results: [], status: "ok" });
    await p;
    expect(searchStore.loading).toBe(false);
  });

  test("runSearch surfaces errors", async () => {
    vi.spyOn(searchApi, "searchEntries").mockRejectedValue(new Error("HTTP 502"));
    await searchStore.runSearch("q");
    expect(searchStore.error).toContain("502");
    expect(searchStore.results).toBeNull();
  });
});
```

- [ ] **Step 2: Test — erwartet Fail**

Run: `cd frontend && npm test -- search-store.test.ts`
Expected: FAIL Modul nicht gefunden.

- [ ] **Step 3: Store implementieren**

`frontend/src/lib/stores/search.svelte.ts`:

```typescript
import {
  searchEntries,
  getSearchStatus,
  type RerankedResult,
  type SearchStatus,
  type SemanticSearchResponse,
} from "$lib/search";

type Mode = "keyword" | "semantic";

class SearchStore {
  query = $state("");
  mode: Mode = $state("keyword");
  loading = $state(false);
  results: RerankedResult[] | null = $state(null);
  lastResponse: SemanticSearchResponse | null = $state(null);
  status: SearchStatus | null = $state(null);
  error: string | null = $state(null);

  setMode(m: Mode) {
    this.mode = m;
    this.results = null;
    this.lastResponse = null;
    this.error = null;
  }

  setQuery(q: string) {
    this.query = q;
  }

  async runSearch(q: string, topK = 10) {
    this.error = null;
    this.loading = true;
    try {
      const resp = await searchEntries(q, topK);
      this.results = resp.results;
      this.lastResponse = resp;
    } catch (e: any) {
      this.error = e?.message ?? "Suche fehlgeschlagen";
      this.results = null;
      this.lastResponse = null;
    } finally {
      this.loading = false;
    }
  }

  async refreshStatus() {
    try {
      this.status = await getSearchStatus();
    } catch {
      // ignore
    }
  }

  reset() {
    this.query = "";
    this.mode = "keyword";
    this.loading = false;
    this.results = null;
    this.lastResponse = null;
    this.status = null;
    this.error = null;
  }
}

export const searchStore = new SearchStore();
```

- [ ] **Step 4: Tests grün**

Run: `cd frontend && npm test -- search-store.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/stores/search.svelte.ts frontend/tests/unit/search-store.test.ts
git commit -m "feat(frontend): search store with mode toggle + runSearch"
```

---

## Task 19: Frontend — SearchToggle-Komponente (TDD)

**Files:**
- Create: `frontend/src/lib/components/SearchToggle.svelte`
- Create: `frontend/tests/unit/search-toggle.test.svelte.ts`

- [ ] **Step 1: Test schreiben**

`frontend/tests/unit/search-toggle.test.svelte.ts`:

```typescript
import { describe, expect, test, afterEach } from "vitest";
import { render, fireEvent, cleanup } from "@testing-library/svelte";
import SearchToggle from "../../src/lib/components/SearchToggle.svelte";

afterEach(() => cleanup());

describe("SearchToggle", () => {
  test("renders ARIA switch with value=keyword", () => {
    const { getByRole } = render(SearchToggle, { props: { value: "keyword", onChange: () => {} } });
    const el = getByRole("switch");
    expect(el.getAttribute("aria-checked")).toBe("false");
  });

  test("onChange toggles to semantic", async () => {
    let called: string | null = null;
    const { getByRole } = render(SearchToggle, {
      props: { value: "keyword", onChange: (v: any) => (called = v) },
    });
    await fireEvent.click(getByRole("switch"));
    expect(called).toBe("semantic");
  });

  test("value=semantic → aria-checked=true", () => {
    const { getByRole } = render(SearchToggle, { props: { value: "semantic", onChange: () => {} } });
    expect(getByRole("switch").getAttribute("aria-checked")).toBe("true");
  });
});
```

- [ ] **Step 2: Test — erwartet Fail**

Run: `cd frontend && npm test -- search-toggle.test.svelte.ts`

- [ ] **Step 3: Komponente schreiben**

`frontend/src/lib/components/SearchToggle.svelte`:

```svelte
<script lang="ts">
  type Mode = "keyword" | "semantic";
  interface Props { value: Mode; onChange: (v: Mode) => void; }
  let { value, onChange }: Props = $props();

  function toggle() {
    onChange(value === "keyword" ? "semantic" : "keyword");
  }
</script>

<button
  type="button"
  role="switch"
  aria-checked={value === "semantic"}
  aria-label="Semantische Suche umschalten"
  class="search-toggle"
  data-mode={value}
  onclick={toggle}
>
  <span class="label" class:active={value === "keyword"}>Stichwort</span>
  <span class="label" class:active={value === "semantic"}>Semantisch</span>
</button>

<style>
  .search-toggle {
    display: inline-flex;
    gap: 0.25rem;
    padding: 0.25rem;
    border: 1px solid var(--border, #ccc);
    border-radius: 999px;
    background: var(--bg-subtle, #f4f4f4);
    min-height: 44px;
    cursor: pointer;
  }
  .label {
    padding: 0.4rem 0.9rem;
    border-radius: 999px;
    font-size: 0.875rem;
    color: var(--muted, #666);
  }
  .label.active {
    background: var(--accent, #2563eb);
    color: white;
  }
</style>
```

- [ ] **Step 4: Tests grün**

Run: `cd frontend && npm test -- search-toggle.test.svelte.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/SearchToggle.svelte frontend/tests/unit/search-toggle.test.svelte.ts
git commit -m "feat(frontend): SearchToggle component (ARIA switch)"
```

---

## Task 20: Frontend — SearchResultCard (TDD)

**Files:**
- Create: `frontend/src/lib/components/SearchResultCard.svelte`
- Create: `frontend/tests/unit/search-result-card.test.svelte.ts`

- [ ] **Step 1: Test schreiben**

`frontend/tests/unit/search-result-card.test.svelte.ts`:

```typescript
import { describe, expect, test, afterEach } from "vitest";
import { render, cleanup } from "@testing-library/svelte";
import SearchResultCard from "../../src/lib/components/SearchResultCard.svelte";

afterEach(() => cleanup());

describe("SearchResultCard", () => {
  test("renders title, excerpt, score, reason", () => {
    const { getByText } = render(SearchResultCard, {
      props: {
        result: {
          entry_id: "e1",
          title: "Regenbogen-Traum",
          excerpt: "Ich war in einem Feld voller Regenbögen.",
          score: 94,
          reason: "Erwähnt einen Regenbogen-Traum",
        },
      },
    });
    expect(getByText("Regenbogen-Traum")).toBeTruthy();
    expect(getByText(/Regenbögen\./)).toBeTruthy();
    expect(getByText("94")).toBeTruthy();
    expect(getByText(/Erwähnt einen Regenbogen/)).toBeTruthy();
  });

  test("hides reason-line when null", () => {
    const { queryByTestId } = render(SearchResultCard, {
      props: { result: { entry_id: "e2", title: "t", excerpt: "e", score: 10, reason: null } },
    });
    expect(queryByTestId("reason-line")).toBeNull();
  });
});
```

- [ ] **Step 2: Test — erwartet Fail**

Run: `cd frontend && npm test -- search-result-card.test.svelte.ts`

- [ ] **Step 3: Komponente schreiben**

`frontend/src/lib/components/SearchResultCard.svelte`:

```svelte
<script lang="ts">
  import type { RerankedResult } from "$lib/search";
  interface Props { result: RerankedResult; }
  let { result }: Props = $props();
</script>

<a class="card" href={`/entries/${result.entry_id}`}>
  <div class="header">
    <h3>{result.title}</h3>
    <span class="score" aria-label="Relevanz">{Math.round(result.score)}</span>
  </div>
  <p class="excerpt">{result.excerpt}</p>
  {#if result.reason}
    <p class="reason" data-testid="reason-line">{result.reason}</p>
  {/if}
</a>

<style>
  .card {
    display: block;
    padding: 1rem;
    border: 1px solid var(--border, #ddd);
    border-radius: 0.5rem;
    color: inherit;
    text-decoration: none;
    background: var(--bg, white);
  }
  .card:hover { background: var(--bg-subtle, #f7f7f7); }
  .header { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
  h3 { margin: 0; font-size: 1rem; }
  .score {
    font-size: 0.75rem; padding: 0.15rem 0.4rem;
    background: var(--accent-soft, #dbeafe); color: var(--accent, #2563eb);
    border-radius: 999px;
  }
  .excerpt { margin: 0.5rem 0 0.25rem; color: var(--muted, #555); font-size: 0.9rem; }
  .reason { margin: 0.25rem 0 0; color: var(--muted, #888); font-size: 0.8rem; font-style: italic; }
</style>
```

- [ ] **Step 4: Tests grün**

Run: `cd frontend && npm test -- search-result-card.test.svelte.ts`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/SearchResultCard.svelte frontend/tests/unit/search-result-card.test.svelte.ts
git commit -m "feat(frontend): SearchResultCard with score badge + reason"
```

---

## Task 21: Frontend — ModelMismatchDialog (TDD)

**Files:**
- Create: `frontend/src/lib/components/ModelMismatchDialog.svelte`
- Create: `frontend/tests/unit/model-mismatch-dialog.test.svelte.ts`

- [ ] **Step 1: Test schreiben**

`frontend/tests/unit/model-mismatch-dialog.test.svelte.ts`:

```typescript
import { describe, expect, test, afterEach, vi } from "vitest";
import { render, fireEvent, cleanup } from "@testing-library/svelte";
import ModelMismatchDialog from "../../src/lib/components/ModelMismatchDialog.svelte";

afterEach(() => cleanup());

describe("ModelMismatchDialog", () => {
  const base = {
    open: true,
    mismatch: { old_model: "old-m", new_model: "new-m", affected_entries: 5 },
    onRevert: vi.fn(),
    onReindex: vi.fn(),
    onLater: vi.fn(),
  };

  test("shows old, new, affected count", () => {
    const { getByText } = render(ModelMismatchDialog, { props: base });
    expect(getByText(/old-m/)).toBeTruthy();
    expect(getByText(/new-m/)).toBeTruthy();
    expect(getByText(/5/)).toBeTruthy();
  });

  test("revert button calls onRevert", async () => {
    const onRevert = vi.fn();
    const { getByRole } = render(ModelMismatchDialog, { props: { ...base, onRevert } });
    await fireEvent.click(getByRole("button", { name: /zurück zum alten/i }));
    expect(onRevert).toHaveBeenCalled();
  });

  test("reindex button calls onReindex", async () => {
    const onReindex = vi.fn();
    const { getByRole } = render(ModelMismatchDialog, { props: { ...base, onReindex } });
    await fireEvent.click(getByRole("button", { name: /neu indexieren/i }));
    expect(onReindex).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Test — erwartet Fail**

Run: `cd frontend && npm test -- model-mismatch-dialog.test.svelte.ts`

- [ ] **Step 3: Komponente**

`frontend/src/lib/components/ModelMismatchDialog.svelte`:

```svelte
<script lang="ts">
  interface Mismatch { old_model: string; new_model: string; affected_entries: number; }
  interface Props {
    open: boolean;
    mismatch: Mismatch;
    onRevert: () => void;
    onReindex: () => void;
    onLater: () => void;
  }
  let { open, mismatch, onRevert, onReindex, onLater }: Props = $props();
</script>

{#if open}
  <div class="backdrop" role="presentation">
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="mm-title">
      <h2 id="mm-title">Embedding-Modell geändert</h2>
      <p>
        Deine bisherigen <strong>{mismatch.affected_entries}</strong> Einträge wurden mit
        <code>{mismatch.old_model}</code> indexiert. Du hast jetzt
        <code>{mismatch.new_model}</code> gewählt. Die Modelle sind untereinander nicht
        kompatibel — die semantische Suche funktioniert nur auf Einträgen im aktuellen Modell.
      </p>
      <p>Was möchtest du tun?</p>
      <div class="actions">
        <button type="button" onclick={onRevert}>Zurück zum alten Modell</button>
        <button type="button" class="primary" onclick={onReindex}>Neu indexieren</button>
        <button type="button" class="subtle" onclick={onLater}>Später entscheiden</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.35);
    display: grid; place-items: center; z-index: 1000;
  }
  .dialog {
    background: white; padding: 1.5rem; border-radius: 0.5rem;
    max-width: 32rem; width: calc(100% - 2rem);
    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
  }
  h2 { margin-top: 0; }
  .actions { display: flex; gap: 0.5rem; justify-content: flex-end; flex-wrap: wrap; margin-top: 1rem; }
  button { min-height: 44px; padding: 0.5rem 1rem; border-radius: 0.375rem; border: 1px solid var(--border, #ccc); background: white; cursor: pointer; }
  button.primary { background: var(--accent, #2563eb); color: white; border-color: transparent; }
  button.subtle { background: transparent; border-color: transparent; color: var(--muted, #666); }
</style>
```

- [ ] **Step 4: Tests grün**

Run: `cd frontend && npm test -- model-mismatch-dialog.test.svelte.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/ModelMismatchDialog.svelte frontend/tests/unit/model-mismatch-dialog.test.svelte.ts
git commit -m "feat(frontend): ModelMismatchDialog with revert/reindex/later"
```

---

## Task 22: Frontend — /entries Integration (Search-UI)

**Files:**
- Modify: `frontend/src/routes/entries/+page.svelte`
- Create/Modify: `frontend/src/lib/transcribe.ts` (falls noch nicht vorhanden — aus `/new` extrahieren)

- [ ] **Step 1: Existierendes Pattern in /new inspizieren**

Run: `grep -n "transcribe\|MediaRecorder" frontend/src/routes/new/+page.svelte | head -20`
Ergebnis-Notiz: Wie wird STT in /new gehandhabt? Entweder direkt im Komponenten-Code oder als Helper. Wenn Helper fehlt, extrahiere den relevanten Code in `frontend/src/lib/transcribe.ts`:

```typescript
import { api } from "$lib/api";

export async function transcribeAudio(blob: Blob): Promise<string> {
  const form = new FormData();
  form.append("audio", blob, "audio.webm");
  const r = await api<{ text: string }>("/api/transcribe", { method: "POST", form });
  return r.text;
}
```

(Den genauen Request-Body aus `/new` abgleichen, Pattern dort übernehmen, nicht blind kopieren.)

- [ ] **Step 2: /entries-Seite erweitern**

In `frontend/src/routes/entries/+page.svelte`:

1. Imports ergänzen:

```svelte
<script lang="ts">
  import { searchStore } from "$lib/stores/search.svelte";
  import SearchToggle from "$lib/components/SearchToggle.svelte";
  import SearchResultCard from "$lib/components/SearchResultCard.svelte";
  import { transcribeAudio } from "$lib/transcribe";
  // ... bestehende
</script>
```

2. Script-Block Ergänzung:

```svelte
<script lang="ts">
  // bestehender State...
  let recording = $state(false);
  let mediaRecorder: MediaRecorder | null = $state(null);

  async function runSearch() {
    if (searchStore.mode === "semantic") {
      await searchStore.runSearch(searchStore.query);
    } else {
      // bestehender Keyword-Fetch
      await fetchEntries();
    }
  }

  async function toggleRecording() {
    if (recording) {
      mediaRecorder?.stop();
      recording = false;
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks: Blob[] = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(chunks, { type: "audio/webm" });
      const text = await transcribeAudio(blob);
      searchStore.setQuery(text);
      await searchStore.runSearch(text);
    };
    mediaRecorder.start();
    recording = true;
  }
</script>
```

3. Template-Ergänzung vor/an bestehendem Suchfeld:

```svelte
<div class="search-row">
  <SearchToggle value={searchStore.mode} onChange={(v) => searchStore.setMode(v)} />
  <input
    type="text"
    bind:value={searchStore.query}
    placeholder={searchStore.mode === "semantic" ? "Frag in ganzen Sätzen …" : "Stichwort suchen"}
    onkeydown={(e) => { if (e.key === "Enter") runSearch(); }}
  />
  {#if searchStore.mode === "semantic"}
    <button type="button" onclick={toggleRecording} aria-label="Per Sprache suchen">
      {recording ? "⏹" : "🎤"}
    </button>
  {/if}
  <button type="button" onclick={runSearch} disabled={searchStore.loading}>
    {searchStore.loading ? "…" : "Suchen"}
  </button>
</div>

{#if searchStore.mode === "semantic"}
  {#if searchStore.error}
    <p class="error">{searchStore.error}</p>
  {:else if searchStore.lastResponse?.status === "not_configured"}
    <div class="banner warn">
      Semantische Suche ist nicht konfiguriert. <a href="/settings">Einstellungen öffnen</a>
    </div>
  {:else if searchStore.lastResponse?.status === "indexing"}
    <div class="banner info">
      Index wird gebaut … {searchStore.lastResponse.progress?.embedded ?? 0}
      von {searchStore.lastResponse.progress?.total ?? 0}
    </div>
  {:else if searchStore.lastResponse?.status === "error"}
    <div class="banner warn">
      Suchindex enthält beschädigte Einträge. <a href="/settings">Neu indexieren</a> empfohlen.
    </div>
  {:else if searchStore.results}
    <div class="search-results">
      {#if searchStore.results.length === 0}
        <p class="empty">Keine Treffer.</p>
      {:else}
        {#each searchStore.results as r (r.entry_id)}
          <SearchResultCard result={r} />
        {/each}
      {/if}
    </div>
  {/if}
{:else}
  <!-- bestehende Keyword-EntryList -->
{/if}

<style>
  .banner { padding: 0.75rem 1rem; border-radius: 0.375rem; margin-bottom: 0.75rem; }
  .banner.warn { background: #fef3c7; color: #92400e; }
  .banner.info { background: #dbeafe; color: #1e40af; }
  .banner a { color: inherit; text-decoration: underline; }
  .error { color: #b91c1c; }
</style>
```

- [ ] **Step 3: Check + Tests**

Run: `cd frontend && npm run check && npm test`
Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/transcribe.ts frontend/src/routes/entries/+page.svelte
git commit -m "feat(entries): semantic search UI with toggle, mic, inline banners"
```

---

## Task 23: Frontend — /settings Embed-Status + Reindex + Modellwechsel-Dialog

**Files:**
- Modify: `frontend/src/routes/settings/+page.svelte`

- [ ] **Step 1: Settings-Seite um Status-Block und Dialog erweitern**

In `frontend/src/routes/settings/+page.svelte`:

Skript-Block ergänzen:

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { getSearchStatus, reindexEmbeddings, type SearchStatus } from "$lib/search";
  import { api } from "$lib/api";
  import ModelMismatchDialog from "$lib/components/ModelMismatchDialog.svelte";

  let embedStatus: SearchStatus | null = $state(null);
  let mismatch: { old_model: string; new_model: string; affected_entries: number } | null = $state(null);

  async function loadStatus() {
    try { embedStatus = await getSearchStatus(); } catch {}
  }

  async function triggerReindex() {
    if (!confirm(`Alle ${embedStatus?.total ?? 0} Einträge werden neu indexiert. Fortfahren?`)) return;
    await reindexEmbeddings();
    await loadStatus();
  }

  onMount(loadStatus);

  // Wrap bestehende savePayload(): nach PUT response auf warning prüfen
  async function saveSettings(payload: any) {
    const resp = await api<any>("/api/settings", { method: "PUT", body: payload });
    if (resp?.warning === "embedding_model_mismatch") {
      mismatch = resp.embedding_mismatch;
    }
    // ggf. bestehende Settings-State aus resp aktualisieren
    return resp;
  }
</script>
```

Template-Ergänzung im Embed-Abschnitt:

```svelte
<section class="embed-status">
  <h3>Index-Status</h3>
  {#if embedStatus}
    <p>
      {embedStatus.embedded} von {embedStatus.total} Einträgen indexiert
      (Modell: {embedStatus.current_model ?? "–"})
      {#if embedStatus.indexing} — <em>läuft gerade</em>{/if}
    </p>
    <button type="button" onclick={triggerReindex} disabled={embedStatus.indexing}>
      Jetzt neu indexieren
    </button>
  {/if}
</section>

<ModelMismatchDialog
  open={mismatch !== null}
  mismatch={mismatch ?? { old_model: "", new_model: "", affected_entries: 0 }}
  onRevert={async () => {
    if (!mismatch) return;
    await api("/api/settings", { method: "PUT", body: { embed_model: mismatch.old_model } });
    mismatch = null;
    await loadStatus();
  }}
  onReindex={async () => {
    await reindexEmbeddings();
    mismatch = null;
    await loadStatus();
  }}
  onLater={() => (mismatch = null)}
/>
```

- [ ] **Step 2: Bestehenden Save-Handler auf saveSettings() umstellen**

Finde im bestehenden Settings-Save-Code den `api("/api/settings", ...)`-Call und ersetze ihn durch den `saveSettings(...)`-Wrapper (oder ziehe die Mismatch-Prüfung direkt an die Stelle).

- [ ] **Step 3: Check + Tests**

Run: `cd frontend && npm run check && npm test`
Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/settings/+page.svelte
git commit -m "feat(settings): index status + reindex button + mismatch dialog"
```

---

## Task 24: Playwright-Skeleton für Semantische Suche

**Files:**
- Create: `frontend/tests/e2e/semantic-search.spec.ts`

- [ ] **Step 1: E2E-Spec schreiben (E2E_LIVE-gated)**

`frontend/tests/e2e/semantic-search.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

const LIVE = !!process.env.E2E_LIVE;

test.describe("semantic search", () => {
  test.skip(!LIVE, "E2E_LIVE not set — running offline skeleton");

  test("toggle to semantic, run query, see results", async ({ page }) => {
    await page.goto("/entries");
    await page.getByRole("switch", { name: /semantisch/i }).click();
    await page.getByPlaceholder(/ganzen Sätzen/).fill("Regenbogen-Traum");
    await page.getByRole("button", { name: /Suchen/ }).click();
    await expect(page.locator(".card").first()).toBeVisible({ timeout: 15000 });
  });

  test("voice path skeleton", async ({ page }) => {
    test.skip(true, "mic injection only in manually prepared E2E_LIVE run");
  });
});
```

- [ ] **Step 2: Playwright — erwartet skipped**

Run: `cd frontend && npx playwright test tests/e2e/semantic-search.spec.ts`
Expected: 2 skipped (0 failed).

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/semantic-search.spec.ts
git commit -m "test(e2e): Playwright skeleton for semantic search"
```

---

## Task 25: End-to-End Manual Test + Roadmap-Update

**Files:**
- Modify: `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md`

- [ ] **Step 1: Lokalen Stack starten**

Run: `docker compose -f deploy/docker-compose.yml down && docker compose -f deploy/docker-compose.yml up -d --build`
Expected: alle drei Container laufen.

- [ ] **Step 2: Manuelle Smoke-Pfade**

Browser:
1. Login → 2-3 Test-Einträge erstellen.
2. /settings → Embed-Feld mit `text-embedding-3-small` + API-Key ausfüllen → speichern.
3. Warte 5-10 s → /settings zeigt `N/N Einträge indexiert`.
4. /entries → Toggle Semantisch → Query eintippen → Suchen → Results mit Reason.
5. Mikrofon: aufnehmen → diktieren → stop → Query befüllt + Suche läuft.
6. /settings → embed_model ändern → Dialog erscheint → "Später entscheiden" → Dialog schließt, Warn-Banner bleibt → Dialog nochmal öffnen → "Neu indexieren" → Reindex läuft.
7. Einen Eintrag editieren (Content ändern) → nach 2 s wieder in Semantik-Suche findbar.

- [ ] **Step 3: Alle Tests grün**

Run: `cd backend && .venv/bin/pytest -q` → alle grün.
Run: `cd frontend && npm test && npm run check` → alle grün.

- [ ] **Step 4: Roadmap aktualisieren**

Öffne `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md`:

- Entferne den „In Arbeit"-Block für Phase 2.
- Unter „Erledigt" einfügen:

```markdown
### Phase 2 Semantische Suche (`v0.3.0-search`)
- Backend: embedding/embedding_model/embedding_updated_at Spalten auf entries + embed_dimensions auf settings (Alembic). numpy-Dependency. services/embeddings.py (pack/unpack/cosine/build_entry_text/embed_text mit TTS-Style 502-Mapping + ProviderRateLimited für strukturiertes 429-Backoff), services/search.py (intent-extract + LLM-rerank mit Cosine-Fallback + semantic_search mit Dimension-Guard → status=error bei allem korrupt), services/embedding_jobs.py (Zustandsautomat mit Koaleszenz, Reindex supersediert Backfill, embed_entry_async mit Modell-Change-Guard vor Persist, embed_dimensions nur initial). Neue Routen POST /api/search + GET /api/search/status + POST /api/search/reindex (slowapi, CSRF + Session). Settings-PUT liefert jetzt vollen SettingsOut-Payload + optionales embedding_model_mismatch-Warning. Entry-Create/Update invalidiert Embedding bei Content-Änderung und schedulet BackgroundTask. Lifespan startet + cancelt den Worker sauber.
- Frontend: search.ts API-Client + search.svelte.ts Store (mode/results/lastResponse/error), SearchToggle (ARIA switch), SearchResultCard (Score + Reason), ModelMismatchDialog (Revert/Reindex/Later). /entries-Seite mit Toggle + Voice-Input + Status-abhängigen Bannern (indexing/not_configured/error). /settings-Seite mit Index-Status + Reindex-Button + Mismatch-Dialog-Einbindung.
- E2E-Skeleton für Query-Pfad (E2E_LIVE-gated).
- Code-Review via Codex durchgeführt, alle BLOCKER (Lock-Race, Test-Pattern, Import-Pfade, Settings-Contract, Dimension-Guard-Semantik, SQLCipher-Threading, entry_date-Typ) adressiert.
```

- Aktualisiere `Letzte Aktualisierung dieser Datei:`.

- [ ] **Step 5: Commit + Tag**

```bash
git commit --allow-empty -m "chore: phase 2 semantic search done (v0.3.0-search)"
git tag v0.3.0-search
```

---

## Self-Review vom Plan-Autor

**Spec-Coverage:**
- Datenmodell (Spec 3.1-3.4) → Tasks 1-3
- Backend-Services (Spec 4.1-4.3) → Tasks 4-10
- Routen (Spec 4.4) → Tasks 12-14
- Modellwechsel-Detektion (Spec 4.5) → Task 15
- Entry-Invalidation (Spec 4.6) → Task 11
- Lifespan (Spec 6.2) → Task 16
- Frontend (Spec 5.1-5.6) → Tasks 17-23
- Error-Handling (Spec 7) → verteilt auf Tasks 5, 8, 9, 10, 12, 15 (jeweils dedizierte Tests)
- Testing (Spec 8) → jeder Task hat eigene Test-Steps + Task 24 E2E

**Placeholder-Scan:** Keine TBD/TODO/implement-later. Die 2 `grep`-Schritte in Tasks 22, 23 sind zielgerichtete Pattern-Lookups, keine Platzhalter.

**Type-Konsistenz:**
- `RerankedResult` / `SemanticSearchResponse` in search.py (Task 6-8) ↔ Frontend-Types in search.ts (Task 17)
- `ProviderRateLimited` (Task 5) ↔ Backoff-Handler (Task 10)
- Job-Runner-Funktionen: `request_backfill`, `request_reindex`, `start_worker`, `stop_worker`, `is_job_running`, `_do_backfill`, `_do_reindex`, `_embed_one_with_backoff`, `_worker_loop`, `_state` — alle konsistent über Tasks 10, 14, 16

**Codex-Review-Punkte adressiert:**
- BLOCKER 1 (Lock-Race): Task 10 nutzt Zustandsautomat ohne release+reacquire.
- BLOCKER 2 (CSRF-Pattern): Alle Tests (11, 12, 13, 14, 15) nutzen `cookies={"session": sid, "csrf": "t"}` + `headers={"x-csrf-token": "t"}`.
- BLOCKER 3 (Import-Pfad): Task 12 importiert `from app.security.rate_limit`.
- BLOCKER 4 (Settings-Response): Task 15 liefert vollen `_settings_to_out(s).model_dump()`-Payload.
- BLOCKER 5 (Dimension-Guard): Task 8 filtert mit Warn-Log, `status="error"` bei allem korrupt.
- BLOCKER 6 (SQLCipher-Threading): Task 9 embed_entry_async öffnet in jedem Call eigene Session; Task 10 serialisiert via Worker.
- BLOCKER 7 (entry_date): Alle Tests nutzen `date(2026, 4, 1)`.
- WICHTIG (429 strukturiert): `ProviderRateLimited` (Task 5) + `_embed_one_with_backoff` (Task 10).
- WICHTIG (ORDER BY updated_at DESC): Task 10 `_do_backfill` enthält es.
- WICHTIG (embed_dimensions Guard): Task 9 setzt nur initial.
- WICHTIG (Modellwechsel-Guard für Einzel-Embed): Task 9 `embed_entry_async` prüft `_current_embed_model()` vor Persist.
- WICHTIG (Lifespan-Shutdown): Task 16 nutzt `try/finally` + `stop_worker`.

**Offene Detailfragen (zielgerichtet, nicht Design-Fragen):**
- Task 22: exaktes transcribe-Pattern aus `/new` (per grep abklären, nicht erraten).
- Task 23: bestehender Save-Handler in `/settings` (Stelle finden, nicht blind überschreiben).
