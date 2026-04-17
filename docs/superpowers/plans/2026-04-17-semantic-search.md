# Semantic Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Natural-language semantic search over all journal entries, toggleable against the existing keyword search, with voice-input support and LLM re-ranking.

**Architecture:** BLOB-column Embeddings auf dem Entry-Model + numpy-Cosine im Backend. LLM extrahiert Kernabsicht aus konversationellen Queries und re-ranked die Top-N. Embedding passiert async nach Save, ein Startup-Backfill holt fehlende Vektoren nach. Modellwechsel löst einen expliziten User-Dialog aus (Revert / Reindex).

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + SQLCipher + numpy (neu) | SvelteKit 2 + Svelte 5 runes + Vitest + Playwright | OpenAI-kompatible `embed`-Capability (existiert bereits im llm_client).

**Projekt-Konvention:** Wir arbeiten direkt auf `main`, keine Feature-Branches. Commits passieren nach jedem Task.

**Spec:** `docs/superpowers/specs/2026-04-17-semantic-search-design.md`

---

## Task 1: numpy-Dependency hinzufügen

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: numpy in requirements.txt aufnehmen**

Füge am Ende von `backend/requirements.txt` hinzu (die exakte Version-Pin matcht zu den anderen Dependencies):

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
Expected: Datei `alembic/versions/<revid>_add_embedding_columns.py` wird erzeugt (Pfad in Output).

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
Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> <revid>, add embedding columns`

- [ ] **Step 4: Schema prüfen**

Run: `cd backend && .venv/bin/python -c "from app.db import engine; from sqlalchemy import inspect; print([c['name'] for c in inspect(engine).get_columns('entries')])"`
Expected: Liste enthält `embedding`, `embedding_model`, `embedding_updated_at`.

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

Öffne `backend/app/models/entry.py` und füge nach der `chat_history`-Zeile ein:

```python
    embedding: Mapped[bytes | None] = mapped_column(sa.LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
```

Importe ergänzen falls nötig — `LargeBinary` kommt aus `sqlalchemy`. Passe den Import-Block oben auf `from sqlalchemy import Date, DateTime, LargeBinary, String, Text, func` an. Wenn `sa` nicht importiert ist, nutze `LargeBinary` direkt:

```python
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
```

- [ ] **Step 2: Settings-Model erweitern**

Öffne `backend/app/models/settings.py` und füge neben den anderen embed-Feldern hinzu:

```python
    embed_dimensions: Mapped[int | None] = mapped_column(Integer)
```

(Falls `Integer` noch nicht importiert ist, ergänze den Import.)

- [ ] **Step 3: Smoke-Test Models importieren**

Run: `cd backend && .venv/bin/python -c "from app.models.entry import Entry; from app.models.settings import AppSettings; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Existierende Tests laufen lassen**

Run: `cd backend && .venv/bin/pytest -q`
Expected: Alle bestehenden Tests grün.

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

- [ ] **Step 1: Test schreiben — pack/unpack/cosine**

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


def test_cosine_similarity_identical_vectors():
    q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    m = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    scores = cosine_similarity(q, m)
    assert scores.shape == (1,)
    assert abs(scores[0] - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    q = np.array([1.0, 0.0], dtype=np.float32)
    m = np.array([[0.0, 1.0]], dtype=np.float32)
    scores = cosine_similarity(q, m)
    assert abs(scores[0] - 0.0) < 1e-6


def test_cosine_similarity_batch():
    q = np.array([1.0, 0.0], dtype=np.float32)
    m = np.array(
        [
            [1.0, 0.0],    # parallel
            [0.0, 1.0],    # orthogonal
            [-1.0, 0.0],   # opposite
        ],
        dtype=np.float32,
    )
    scores = cosine_similarity(q, m)
    assert scores.shape == (3,)
    assert abs(scores[0] - 1.0) < 1e-6
    assert abs(scores[1]) < 1e-6
    assert abs(scores[2] + 1.0) < 1e-6
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.services.embeddings'`.

- [ ] **Step 3: Implementation schreiben**

`backend/app/services/embeddings.py`:

```python
"""Embedding vector operations for semantic search.

Pack/unpack: float32 numpy arrays ↔ bytes (for BLOB storage).
Cosine similarity: vectorized over a candidate matrix.
"""
from __future__ import annotations

import numpy as np


def pack_vector(vec: np.ndarray) -> bytes:
    """Serialize a 1D float32 array to bytes suitable for a LargeBinary column."""
    return np.asarray(vec, dtype=np.float32).tobytes()


def unpack_vector(blob: bytes) -> np.ndarray:
    """Deserialize bytes produced by pack_vector back into a float32 array."""
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(query: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    """Cosine similarity between a query vector and N candidate vectors.

    query:      shape (D,)
    candidates: shape (N, D)
    returns:    shape (N,) of similarity scores in [-1, 1].
    """
    q = query.astype(np.float32)
    m = candidates.astype(np.float32)
    q_norm = np.linalg.norm(q)
    m_norms = np.linalg.norm(m, axis=1)
    denom = q_norm * m_norms
    denom = np.where(denom == 0, 1.0, denom)
    return (m @ q) / denom
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embeddings.py backend/tests/test_embeddings_service.py
git commit -m "feat(embeddings): vector pack/unpack + cosine similarity"
```

---

## Task 5: Embeddings-Service — build_entry_text + embed_text (TDD)

**Files:**
- Modify: `backend/app/services/embeddings.py`
- Modify: `backend/tests/test_embeddings_service.py`

- [ ] **Step 1: Tests ergänzen für build_entry_text**

Oben in `tests/test_embeddings_service.py` hinzufügen:

```python
from types import SimpleNamespace


def test_build_entry_text_concatenates_title_and_content():
    from app.services.embeddings import build_entry_text

    e = SimpleNamespace(title="Der Regenbogen-Traum", content="Ich träumte von einem Regenbogen.")
    out = build_entry_text(e)
    assert out == "Der Regenbogen-Traum\n\nIch träumte von einem Regenbogen."


def test_build_entry_text_truncates_at_limit():
    from app.services.embeddings import build_entry_text, MAX_EMBED_CHARS

    long_content = "x" * (MAX_EMBED_CHARS * 2)
    e = SimpleNamespace(title="t", content=long_content)
    out = build_entry_text(e)
    assert len(out) <= MAX_EMBED_CHARS
```

- [ ] **Step 2: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py::test_build_entry_text_concatenates_title_and_content -v`
Expected: FAIL mit `ImportError: cannot import name 'build_entry_text'`.

- [ ] **Step 3: Implementation ergänzen**

In `backend/app/services/embeddings.py` oben ergänzen und neue Funktion hinzufügen:

```python
MAX_EMBED_CHARS = 28000  # ~7k tokens at ~4 chars/token heuristic


def build_entry_text(entry) -> str:
    """Canonical embedding input: title + blank line + content, truncated."""
    text = f"{entry.title}\n\n{entry.content}"
    if len(text) > MAX_EMBED_CHARS:
        text = text[:MAX_EMBED_CHARS]
    return text
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py -v`
Expected: 6 passed.

- [ ] **Step 5: Tests für embed_text schreiben**

Am Ende von `tests/test_embeddings_service.py` hinzufügen:

```python
import httpx
import pytest
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


def test_embed_text_returns_vector_and_model():
    from app.services.embeddings import embed_text

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
                    "model": "text-embedding-3-small",
                },
            )
        )
        vec, model = embed_text("Hallo Welt")

    assert vec.dtype == np.float32
    assert vec.shape == (4,)
    assert model == "text-embedding-3-small"


def test_embed_text_maps_5xx_to_502():
    from app.services.embeddings import embed_text

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(500, json={"error": "boom"}))
        with pytest.raises(Exception) as ei:
            embed_text("test")

    assert "502" in str(ei.value) or "embedding" in str(ei.value).lower()


def test_embed_text_maps_connect_error_to_502():
    from app.services.embeddings import embed_text

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(Exception) as ei:
            embed_text("test")

    assert "502" in str(ei.value) or "embedding" in str(ei.value).lower()
```

- [ ] **Step 6: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py::test_embed_text_returns_vector_and_model -v`
Expected: FAIL mit `ImportError: cannot import name 'embed_text'`.

- [ ] **Step 7: embed_text implementieren**

In `backend/app/services/embeddings.py` unten ergänzen:

```python
from fastapi import HTTPException

from app.services.llm_client import get_client


def embed_text(text: str) -> tuple[np.ndarray, str]:
    """Call the embed-capability and return (vector, model_name).

    Error mapping mirrors services/tts.py: any transport or 4xx/5xx is
    surfaced as HTTPException(502, ...) so callers get a consistent shape.
    """
    client, model = get_client("embed")
    try:
        resp = client.embeddings.create(model=model, input=text)
    except Exception as e:
        raise HTTPException(502, f"embedding service error: {e}") from e

    try:
        raw = resp.data[0].embedding
        resolved_model = getattr(resp, "model", None) or model
    except (AttributeError, IndexError) as e:
        raise HTTPException(502, f"embedding service returned unexpected shape: {e}") from e

    return np.asarray(raw, dtype=np.float32), resolved_model
```

- [ ] **Step 8: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_embeddings_service.py -v`
Expected: alle (9) grün.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/embeddings.py backend/tests/test_embeddings_service.py
git commit -m "feat(embeddings): build_entry_text + embed_text with 502 mapping"
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

    raw = "Hey, ich habe doch mal darüber gesprochen, dass ich einen Traum mit Regenbögen hatte. Zeig mir die entsprechenden Einträge."
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "Traum mit Regenbögen"}}],
                    "model": "gpt-4o-mini",
                },
            )
        )
        out = extract_search_intent(raw)
    assert out == "Traum mit Regenbögen"


def test_extract_search_intent_falls_back_on_error():
    from app.services.search import extract_search_intent

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(side_effect=httpx.ConnectError("down"))
        out = extract_search_intent("was auch immer")
    # Fallback: raw query returned untouched
    assert out == "was auch immer"
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.services.search'`.

- [ ] **Step 3: Implementation schreiben**

`backend/app/services/search.py`:

```python
"""Semantic search orchestration.

extract_search_intent: compress conversational queries to a search phrase.
rerank_results:        LLM-based re-ranking of top-N cosine candidates.
semantic_search:       end-to-end pipeline for POST /api/search.
"""
from __future__ import annotations

import logging

from app.services.llm_client import get_client

log = logging.getLogger(__name__)

SEARCH_INTENT_PROMPT = (
    "Du bist ein Suchhilfsmodul. Der Nutzer spricht in ganzen Sätzen und "
    "fragt nach Tagebucheinträgen. Extrahiere die inhaltliche Kernabsicht "
    "als kurze, suchfreundliche Phrase (maximal 10 Wörter, keine Begrüßung, "
    "keine Höflichkeitsfloskeln). Antworte nur mit der Phrase, ohne "
    "Anführungszeichen, ohne Erklärung."
)


def extract_search_intent(query: str) -> str:
    """Reduce a conversational query to its search phrase.

    On any failure, returns the original query unchanged (graceful
    degradation — direct embedding of the raw query still works).
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
    except Exception as e:
        log.warning("extract_search_intent failed, falling back to raw query: %s", e)
        return query
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search.py backend/tests/test_search_service.py
git commit -m "feat(search): extract_search_intent with graceful fallback"
```

---

## Task 7: Search-Service — rerank_results (TDD)

**Files:**
- Modify: `backend/app/services/search.py`
- Modify: `backend/tests/test_search_service.py`

- [ ] **Step 1: RerankedResult Schema in Plan einführen — Tests erweitern**

Am Ende von `tests/test_search_service.py` ergänzen:

```python
from types import SimpleNamespace


def _fake_entry(eid, title, content):
    return SimpleNamespace(id=eid, title=title, content=content)


def test_rerank_results_parses_json_response():
    from app.services.search import rerank_results

    candidates = [
        _fake_entry("e1", "Regenbogen-Traum", "Ich war in einem Feld voller Regenbögen."),
        _fake_entry("e2", "Urlaub am Meer", "Strand und Wellen."),
    ]
    rerank_json = (
        '[{"id":"e1","score":92,"reason":"Erwähnt einen Regenbogen-Traum"},'
        '{"id":"e2","score":12,"reason":"Kein Bezug"}]'
    )
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": rerank_json}}],
                    "model": "gpt-4o-mini",
                },
            )
        )
        out = rerank_results("Regenbogen-Traum", candidates, top_k=2)

    assert [r.entry_id for r in out] == ["e1", "e2"]
    assert out[0].score == 92
    assert out[0].reason == "Erwähnt einen Regenbogen-Traum"


def test_rerank_results_falls_back_to_cosine_on_bad_json():
    from app.services.search import rerank_results

    candidates = [
        _fake_entry("e1", "A", "a"),
        _fake_entry("e2", "B", "b"),
    ]
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "not valid json at all"}}],
                    "model": "gpt-4o-mini",
                },
            )
        )
        out = rerank_results("q", candidates, top_k=2)

    assert len(out) == 2
    assert all(r.reason is None for r in out)


def test_rerank_results_falls_back_on_http_error():
    from app.services.search import rerank_results

    candidates = [_fake_entry("e1", "A", "a")]
    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/chat/completions").mock(side_effect=httpx.ConnectError("down"))
        out = rerank_results("q", candidates, top_k=1)

    assert [r.entry_id for r in out] == ["e1"]
    assert out[0].reason is None
```

- [ ] **Step 2: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py::test_rerank_results_parses_json_response -v`
Expected: FAIL mit `ImportError: cannot import name 'rerank_results'`.

- [ ] **Step 3: RerankedResult Pydantic-Modell + rerank_results schreiben**

In `backend/app/services/search.py` ergänzen (oben neben den anderen Imports):

```python
import json

from pydantic import BaseModel


class RerankedResult(BaseModel):
    entry_id: str
    title: str
    excerpt: str
    score: float
    reason: str | None = None
```

Und unten anfügen:

```python
RERANK_PROMPT = (
    "Du bekommst eine Nutzeranfrage und eine Liste von Tagebucheintrag-"
    "Kandidaten (id, title, snippet). Bewerte jeden Kandidaten mit einem "
    "Score von 0 bis 100 für die inhaltliche Relevanz zur Anfrage und "
    "beschreibe in einem kurzen Satz (max. 120 Zeichen) warum. "
    'Antworte AUSSCHLIESSLICH mit einem JSON-Array der Form '
    '[{"id":"...","score":0-100,"reason":"..."}, ...]. '
    "Keine Erklärung, kein Markdown, kein Text drumherum."
)


def _excerpt(text: str, limit: int = 200) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def rerank_results(query: str, candidates: list, top_k: int) -> list[RerankedResult]:
    """LLM-rerank. Falls back to cosine-order + reason=None on any failure."""
    if not candidates:
        return []

    # Build the fallback list up front (cosine order preserved, no reason).
    fallback = [
        RerankedResult(
            entry_id=c.id,
            title=c.title,
            excerpt=_excerpt(c.content),
            score=0.0,
            reason=None,
        )
        for c in candidates[:top_k]
    ]

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
        # Provider may wrap in {"results":[...]} with json_object mode.
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            arr = parsed.get("results") or parsed.get("items") or next(
                (v for v in parsed.values() if isinstance(v, list)), None
            )
        else:
            arr = parsed
        if not isinstance(arr, list):
            raise ValueError("rerank response is not a list")

        by_id = {c.id: c for c in candidates}
        out: list[RerankedResult] = []
        for item in arr:
            cid = item.get("id")
            cand = by_id.get(cid)
            if cand is None:
                continue
            out.append(
                RerankedResult(
                    entry_id=cid,
                    title=cand.title,
                    excerpt=_excerpt(cand.content),
                    score=float(item.get("score", 0)),
                    reason=item.get("reason"),
                )
            )
        if not out:
            return fallback
        return out[:top_k]
    except Exception as e:
        log.warning("rerank_results failed, falling back to cosine order: %s", e)
        return fallback
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search.py backend/tests/test_search_service.py
git commit -m "feat(search): LLM rerank with cosine-order fallback"
```

---

## Task 8: Search-Service — semantic_search Orchestrierung (TDD)

**Files:**
- Modify: `backend/app/services/search.py`
- Modify: `backend/tests/test_search_service.py`

- [ ] **Step 1: Test schreiben**

Am Ende von `tests/test_search_service.py` ergänzen:

```python
import json as _json
import numpy as np

from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import pack_vector


def _seed_entry(db, eid, title, content, vec, model):
    e = Entry(
        id=eid,
        entry_date="2026-04-01",
        title=title,
        content=content,
        embedding=pack_vector(vec),
        embedding_model=model,
    )
    db.add(e)


def test_semantic_search_end_to_end():
    from app.services.search import semantic_search

    # Seed: three entries, current model + one with outdated model
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.embed_model = "text-embedding-3-small"
        db.query(Entry).delete()
        _seed_entry(db, "e1", "Regenbogen-Traum", "Ich sah Regenbögen.",
                    np.array([1.0, 0.0, 0.0], dtype=np.float32), "text-embedding-3-small")
        _seed_entry(db, "e2", "Auto-Kauf", "Neues Auto angeschafft.",
                    np.array([0.0, 1.0, 0.0], dtype=np.float32), "text-embedding-3-small")
        _seed_entry(db, "e3", "Ältere Sache", "alt",
                    np.array([1.0, 0.0, 0.0], dtype=np.float32), "old-model")
        db.commit()

    intent_resp = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "Regenbogen"}}], "model": "chat"},
    )
    embed_resp = httpx.Response(
        200,
        json={"data": [{"embedding": [1.0, 0.0, 0.0]}], "model": "text-embedding-3-small"},
    )
    rerank_json = '[{"id":"e1","score":95,"reason":"Match"}]'
    rerank_resp = httpx.Response(
        200,
        json={"choices": [{"message": {"content": rerank_json}}], "model": "chat"},
    )

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        # Two chat calls (intent + rerank) and one embedding call
        chat_route = mock.post("/chat/completions").mock(side_effect=[intent_resp, rerank_resp])
        mock.post("/embeddings").mock(return_value=embed_resp)
        result = semantic_search("Hey, Regenbogen-Traum?", top_k=5)

    # e3 filtered out by outdated model; e1 wins by cosine + rerank
    assert result.status == "ok"
    assert [r.entry_id for r in result.results] == ["e1"]
    assert result.results[0].reason == "Match"
    assert chat_route.call_count == 2
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py::test_semantic_search_end_to_end -v`
Expected: FAIL mit `ImportError: cannot import name 'semantic_search'`.

- [ ] **Step 3: Response-Modell + semantic_search implementieren**

In `backend/app/services/search.py` ergänzen:

```python
from typing import Literal

from sqlalchemy import select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import cosine_similarity, embed_text, unpack_vector


class SemanticSearchResponse(BaseModel):
    results: list[RerankedResult]
    status: Literal["ok", "indexing", "not_configured"]
    progress: dict | None = None


RERANK_POOL_SIZE = 30


def semantic_search(query: str, top_k: int = 10) -> SemanticSearchResponse:
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
        total = db.execute(select(Entry.id)).scalars().all()
        total_count = len(total)
        embedded_count = len(rows)

    if not rows:
        return SemanticSearchResponse(
            results=[],
            status="indexing",
            progress={"embedded": embedded_count, "total": total_count},
        )

    intent = extract_search_intent(query)
    query_vec, _ = embed_text(intent)

    # Dimension guard: filter rows whose vector length doesn't match.
    candidates = []
    vectors = []
    for e in rows:
        v = unpack_vector(e.embedding)
        if v.shape[0] == query_vec.shape[0]:
            candidates.append(e)
            vectors.append(v)

    if not candidates:
        return SemanticSearchResponse(
            results=[],
            status="indexing",
            progress={"embedded": embedded_count, "total": total_count},
        )

    import numpy as np
    matrix = np.stack(vectors)
    scores = cosine_similarity(query_vec, matrix)
    order = np.argsort(scores)[::-1][:RERANK_POOL_SIZE]
    pool = [candidates[i] for i in order]

    reranked = rerank_results(query, pool, top_k=top_k)
    return SemanticSearchResponse(results=reranked, status="ok")
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_search_service.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search.py backend/tests/test_search_service.py
git commit -m "feat(search): end-to-end semantic_search pipeline"
```

---

## Task 9: Embedding-Jobs — embed_entry_async (TDD)

**Files:**
- Create: `backend/app/services/embedding_jobs.py`
- Create: `backend/tests/test_embedding_jobs.py`

- [ ] **Step 1: Test schreiben**

`backend/tests/test_embedding_jobs.py`:

```python
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


def test_embed_entry_async_populates_embedding():
    from app.services.embedding_jobs import embed_entry_async

    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="e1", entry_date="2026-04-01", title="t", content="c"))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"embedding": [0.1, 0.2, 0.3]}], "model": "m1"},
            )
        )
        embed_entry_async("e1")

    with SessionLocal() as db:
        e = db.get(Entry, "e1")
        assert e.embedding is not None
        assert e.embedding_model == "m1"
        assert e.embedding_updated_at is not None
        vec = unpack_vector(e.embedding)
        assert vec.shape == (3,)


def test_embed_entry_async_skips_if_entry_gone():
    from app.services.embedding_jobs import embed_entry_async

    _reset_entries()
    # Call against missing id — must not crash
    embed_entry_async("does-not-exist")


def test_embed_entry_async_tolerates_embed_failure():
    from app.services.embedding_jobs import embed_entry_async

    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(id="e2", entry_date="2026-04-01", title="t", content="c"))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(return_value=httpx.Response(500, json={"error": "boom"}))
        embed_entry_async("e2")  # should not raise

    with SessionLocal() as db:
        e = db.get(Entry, "e2")
        assert e.embedding is None  # unchanged, no crash
```

- [ ] **Step 2: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embedding_jobs.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.services.embedding_jobs'`.

- [ ] **Step 3: Implementation schreiben**

`backend/app/services/embedding_jobs.py`:

```python
"""Background/startup jobs for maintaining entry embeddings."""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import or_, select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import build_entry_text, embed_text, pack_vector
from app.utc import utc_now

log = logging.getLogger(__name__)

BACKFILL_THROTTLE_SECONDS = 0.2
BACKOFF_STEPS = (1.0, 2.0, 4.0)

_job_lock = asyncio.Lock()


def embed_entry_async(entry_id: str) -> None:
    """Compute + persist embedding for a single entry.

    Safe to call from a FastAPI BackgroundTask. Silently skips if the entry
    is gone (race with DELETE) or if the embed-call fails.
    """
    with SessionLocal() as db:
        e = db.get(Entry, entry_id)
        if e is None:
            return
        text = build_entry_text(e)

    try:
        vec, model = embed_text(text)
    except Exception as err:
        log.warning("embed failed for entry %s: %s", entry_id, err)
        return

    blob = pack_vector(vec)
    with SessionLocal() as db:
        e = db.get(Entry, entry_id)
        if e is None:
            return  # deleted between embed + write
        e.embedding = blob
        e.embedding_model = model
        e.embedding_updated_at = utc_now()
        db.commit()

        # Persist dimension on first success, for Settings sanity checks.
        s = db.get(AppSettings, 1)
        if s is not None and s.embed_dimensions != vec.shape[0]:
            s.embed_dimensions = int(vec.shape[0])
            db.commit()
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_embedding_jobs.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embedding_jobs.py backend/tests/test_embedding_jobs.py
git commit -m "feat(jobs): embed_entry_async with delete-race + failure tolerance"
```

---

## Task 10: Embedding-Jobs — backfill_missing + reindex_all (TDD)

**Files:**
- Modify: `backend/app/services/embedding_jobs.py`
- Modify: `backend/tests/test_embedding_jobs.py`

- [ ] **Step 1: Tests ergänzen**

Am Ende von `tests/test_embedding_jobs.py`:

```python
def test_backfill_fills_missing_and_skips_matching_model():
    import asyncio as _a
    from app.services.embedding_jobs import backfill_missing_embeddings
    from app.services.embeddings import pack_vector

    _reset_entries()
    with SessionLocal() as db:
        # one without embedding
        db.add(Entry(id="a", entry_date="2026-04-01", title="a", content="c"))
        # one with outdated model
        db.add(Entry(
            id="b", entry_date="2026-04-01", title="b", content="c",
            embedding=pack_vector(np.array([0.0, 1.0], dtype=np.float32)),
            embedding_model="old-model",
        ))
        # one already current — should be skipped
        db.add(Entry(
            id="c", entry_date="2026-04-01", title="c", content="c",
            embedding=pack_vector(np.array([1.0, 0.0], dtype=np.float32)),
            embedding_model="m1",
        ))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        route = mock.post("/embeddings").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"embedding": [0.5, 0.5]}], "model": "m1"},
            )
        )
        _a.run(backfill_missing_embeddings())

    # a and b were re-embedded (2 calls), c was not
    assert route.call_count == 2

    with SessionLocal() as db:
        for eid in ("a", "b"):
            e = db.get(Entry, eid)
            assert e.embedding_model == "m1"


def test_reindex_all_nulls_and_refills():
    import asyncio as _a
    from app.services.embedding_jobs import reindex_all
    from app.services.embeddings import pack_vector

    _reset_entries()
    with SessionLocal() as db:
        db.add(Entry(
            id="z", entry_date="2026-04-01", title="z", content="c",
            embedding=pack_vector(np.array([1.0], dtype=np.float32)),
            embedding_model="m1",
        ))
        db.commit()

    with respx.mock(base_url="https://api.openai.com/v1") as mock:
        mock.post("/embeddings").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"embedding": [0.9, 0.1]}], "model": "m1"},
            )
        )
        _a.run(reindex_all())

    with SessionLocal() as db:
        e = db.get(Entry, "z")
        assert unpack_vector(e.embedding).shape == (2,)
```

- [ ] **Step 2: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_embedding_jobs.py::test_backfill_fills_missing_and_skips_matching_model -v`
Expected: FAIL mit `ImportError: cannot import name 'backfill_missing_embeddings'`.

- [ ] **Step 3: Implementation ergänzen**

In `backend/app/services/embedding_jobs.py` unten ergänzen:

```python
def _current_embed_model() -> str | None:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        return s.embed_model if s else None


async def backfill_missing_embeddings() -> None:
    """Find entries whose embedding is missing or out-of-date, then embed them.

    Runs under a module-global asyncio lock so parallel triggers
    (startup + manual reindex) can't race.
    """
    if _job_lock.locked():
        log.info("backfill skipped: another job is running")
        return
    async with _job_lock:
        current = _current_embed_model()
        if not current:
            log.info("backfill skipped: no embed_model configured")
            return

        with SessionLocal() as db:
            ids = db.execute(
                select(Entry.id).where(
                    or_(
                        Entry.embedding.is_(None),
                        Entry.embedding_model != current,
                    )
                )
            ).scalars().all()

        log.info("backfill: %d entries pending", len(ids))
        for eid in ids:
            # embed_entry_async is sync; run in thread to avoid blocking loop.
            await asyncio.to_thread(embed_entry_async, eid)
            await asyncio.sleep(BACKFILL_THROTTLE_SECONDS)


async def reindex_all() -> None:
    """Null every embedding, then run backfill."""
    # We briefly release the lock so backfill can re-acquire it.
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
    await backfill_missing_embeddings()


def is_backfill_running() -> bool:
    return _job_lock.locked()
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_embedding_jobs.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embedding_jobs.py backend/tests/test_embedding_jobs.py
git commit -m "feat(jobs): backfill_missing_embeddings + reindex_all with job lock"
```

---

## Task 11: Entry-Routen — Embedding-Invalidation + BackgroundTask (TDD)

**Files:**
- Modify: `backend/app/routes/entries.py`
- Modify: `backend/tests/test_entries.py` (oder neue Testdatei `test_entries_embedding.py`)

- [ ] **Step 1: Neue Testdatei schreiben**

`backend/tests/test_entries_embedding.py`:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import pack_vector

import numpy as np


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


def _auth_client() -> TestClient:
    c = TestClient(app)
    sid = create_session()
    c.cookies.set("sid", sid)
    r = c.get("/api/session/csrf")
    c.headers["X-CSRF"] = r.json()["csrf"]
    return c


def test_create_entry_schedules_embedding_task():
    c = _auth_client()
    with patch("app.routes.entries.embed_entry_async") as mock_embed:
        r = c.post(
            "/api/entries",
            json={"entry_date": "2026-04-01", "title": "x", "content": "y", "tags": []},
        )
    assert r.status_code == 201
    # BackgroundTask scheduling records the entry_id as its argument
    mock_embed.assert_called_once()
    assert mock_embed.call_args.args[0] == r.json()["id"]


def test_update_entry_content_invalidates_embedding():
    c = _auth_client()
    with SessionLocal() as db:
        e = Entry(
            id="upd1", entry_date="2026-04-01", title="old", content="old-content",
            embedding=pack_vector(np.array([1.0, 0.0], dtype=np.float32)),
            embedding_model="m1",
        )
        db.add(e)
        db.commit()

    with patch("app.routes.entries.embed_entry_async") as mock_embed:
        r = c.put("/api/entries/upd1", json={"content": "NEW-content"})

    assert r.status_code == 200
    with SessionLocal() as db:
        e = db.get(Entry, "upd1")
        assert e.embedding is None
        assert e.embedding_model is None
    mock_embed.assert_called_once_with("upd1")


def test_update_entry_tags_only_keeps_embedding():
    c = _auth_client()
    with SessionLocal() as db:
        db.query(Entry).filter(Entry.id == "upd2").delete()
        e = Entry(
            id="upd2", entry_date="2026-04-01", title="t", content="c",
            embedding=pack_vector(np.array([1.0, 0.0], dtype=np.float32)),
            embedding_model="m1",
        )
        db.add(e)
        db.commit()

    with patch("app.routes.entries.embed_entry_async") as mock_embed:
        r = c.put("/api/entries/upd2", json={"tags": ["happy"]})

    assert r.status_code == 200
    with SessionLocal() as db:
        e = db.get(Entry, "upd2")
        assert e.embedding is not None
        assert e.embedding_model == "m1"
    mock_embed.assert_not_called()
```

- [ ] **Step 2: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_entries_embedding.py -v`
Expected: FAIL — entweder Import-Fehler (`embed_entry_async` noch nicht in routes importiert) oder Tests failen, weil die Invalidation-Logik fehlt.

- [ ] **Step 3: routes/entries.py erweitern**

In `backend/app/routes/entries.py`:

1. Import ergänzen, oben:

```python
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.services.embedding_jobs import embed_entry_async
```

2. `create_entry` Signature und Body anpassen:

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

3. `update_entry` anpassen — Text-Änderungen nullen das Embedding:

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

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_entries_embedding.py -v`
Expected: 3 passed.

- [ ] **Step 5: Bestehende entries-Tests weiter grün**

Run: `cd backend && .venv/bin/pytest tests/test_entries.py -v`
Expected: alle bisherigen Tests bestanden.

- [ ] **Step 6: Commit**

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

- [ ] **Step 1: Route in main.py registrieren (Placeholder)**

In `backend/app/main.py` an die Stelle wo die anderen Router includiert werden:

```python
from app.routes import search as search_routes
...
app.include_router(search_routes.router)
```

(Noch fehlt das Modul — Commit später zusammen mit Implementation.)

- [ ] **Step 2: Test schreiben**

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


def _auth_client():
    c = TestClient(app)
    sid = create_session()
    c.cookies.set("sid", sid)
    r = c.get("/api/session/csrf")
    c.headers["X-CSRF"] = r.json()["csrf"]
    return c


def test_post_search_returns_results():
    c = _auth_client()
    fake_resp = SemanticSearchResponse(
        results=[RerankedResult(entry_id="e1", title="T", excerpt="E", score=90.0, reason="why")],
        status="ok",
    )
    with patch("app.routes.search.semantic_search", return_value=fake_resp) as ss:
        r = c.post("/api/search", json={"query": "Regenbogen", "top_k": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["results"][0]["entry_id"] == "e1"
    assert body["results"][0]["reason"] == "why"
    ss.assert_called_once_with("Regenbogen", top_k=5)


def test_post_search_requires_session():
    c = TestClient(app)
    r = c.post("/api/search", json={"query": "x"})
    assert r.status_code == 401


def test_post_search_requires_csrf():
    c = TestClient(app)
    sid = create_session()
    c.cookies.set("sid", sid)
    # no CSRF header
    r = c.post("/api/search", json={"query": "x"})
    assert r.status_code == 403
```

- [ ] **Step 3: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py::test_post_search_returns_results -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.routes.search'`.

- [ ] **Step 4: Route-Modul schreiben**

`backend/app/routes/search.py`:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from slowapi.util import get_remote_address

from app.rate_limit import limiter
from app.services.search import semantic_search

router = APIRouter(prefix="/api/search")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)


@router.post("")
@limiter.limit("30/minute")
async def search(request, body: SearchRequest) -> dict:
    if not body.query.strip():
        raise HTTPException(400, "empty query")
    result = semantic_search(body.query.strip(), top_k=body.top_k)
    return result.model_dump()
```

**Hinweis zur slowapi-Signatur:** Der erste Positional-Parameter heißt konventionell `request`. Wenn die bestehenden Routen anders geschrieben sind, das Pattern übernehmen — prüfe mit: `grep -n "limiter.limit" backend/app/routes/*.py`.

- [ ] **Step 5: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/search.py backend/app/main.py backend/tests/test_search_routes.py
git commit -m "feat(api): POST /api/search with rate-limit, session, CSRF"
```

---

## Task 13: Search-Route — GET /api/search/status (TDD)

**Files:**
- Modify: `backend/app/routes/search.py`
- Modify: `backend/tests/test_search_routes.py`

- [ ] **Step 1: Test ergänzen**

Am Ende von `tests/test_search_routes.py`:

```python
import numpy as np
from app.services.embeddings import pack_vector


def _seed_entries(total_with_emb, total_without_emb, model):
    with SessionLocal() as db:
        db.query(Entry).delete()
        for i in range(total_with_emb):
            db.add(Entry(
                id=f"w{i}", entry_date="2026-04-01", title=f"w{i}", content="c",
                embedding=pack_vector(np.array([1.0], dtype=np.float32)),
                embedding_model=model,
            ))
        for i in range(total_without_emb):
            db.add(Entry(id=f"n{i}", entry_date="2026-04-01", title=f"n{i}", content="c"))
        db.commit()


def test_search_status_reports_counts():
    c = _auth_client()
    _seed_entries(3, 2, model="m1")
    r = c.get("/api/search/status")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["embedded"] == 3
    assert body["pending"] == 2
    assert body["current_model"] == "m1"
    assert body["configured"] is True


def test_search_status_not_configured_when_model_unset():
    c = _auth_client()
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = None
        db.commit()
    r = c.get("/api/search/status")
    assert r.status_code == 200
    assert r.json()["configured"] is False
    # restore for later tests
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "m1"
        db.commit()
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py::test_search_status_reports_counts -v`
Expected: FAIL 404 (Route existiert noch nicht).

- [ ] **Step 3: Route ergänzen**

In `backend/app/routes/search.py` unten hinzufügen:

```python
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embedding_jobs import is_backfill_running


@router.get("/status")
async def search_status() -> dict:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        current = s.embed_model if s else None
        total = db.scalar(select(func.count()).select_from(Entry)) or 0
        embedded = db.scalar(
            select(func.count()).select_from(Entry).where(
                Entry.embedding.is_not(None),
                Entry.embedding_model == current,
            )
        ) or 0
    return {
        "total": int(total),
        "embedded": int(embedded),
        "pending": int(total) - int(embedded),
        "current_model": current,
        "configured": bool(current),
        "indexing": is_backfill_running(),
    }
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/search.py backend/tests/test_search_routes.py
git commit -m "feat(api): GET /api/search/status with counts and configured flag"
```

---

## Task 14: Search-Route — POST /api/search/reindex (TDD)

**Files:**
- Modify: `backend/app/routes/search.py`
- Modify: `backend/tests/test_search_routes.py`

- [ ] **Step 1: Test ergänzen**

Am Ende von `tests/test_search_routes.py`:

```python
def test_post_reindex_triggers_job():
    c = _auth_client()
    with patch("app.routes.search.reindex_all") as mock_reindex:
        mock_reindex.return_value = None
        r = c.post("/api/search/reindex")
    assert r.status_code == 202
    mock_reindex.assert_called_once()


def test_post_reindex_requires_csrf():
    c = TestClient(app)
    sid = create_session()
    c.cookies.set("sid", sid)
    r = c.post("/api/search/reindex")
    assert r.status_code == 403


def test_post_reindex_conflicts_when_running():
    c = _auth_client()
    with patch("app.routes.search.is_backfill_running", return_value=True):
        r = c.post("/api/search/reindex")
    assert r.status_code == 409
```

- [ ] **Step 2: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py::test_post_reindex_triggers_job -v`
Expected: FAIL 404.

- [ ] **Step 3: Route ergänzen**

In `backend/app/routes/search.py`:

```python
import asyncio

from app.services.embedding_jobs import reindex_all


@router.post("/reindex", status_code=202)
@limiter.limit("1/minute")
async def reindex(request) -> dict:
    if is_backfill_running():
        raise HTTPException(409, "reindex or backfill already running")
    asyncio.create_task(reindex_all())
    return {"ok": True}
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_search_routes.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/search.py backend/tests/test_search_routes.py
git commit -m "feat(api): POST /api/search/reindex with 409 when already running"
```

---

## Task 15: Settings-PUT — Modellwechsel-Warning (TDD)

**Files:**
- Modify: `backend/app/routes/settings.py`
- Modify: `backend/tests/test_settings_routes.py`

- [ ] **Step 1: Test schreiben**

Am Ende von `backend/tests/test_settings_routes.py` ergänzen (vorher bestehende Imports prüfen — `Entry` muss importiert werden):

```python
from app.models.entry import Entry
from app.services.embeddings import pack_vector
import numpy as _np


def test_settings_put_warns_on_embed_model_change_with_existing_entries():
    c = _auth_client()
    with SessionLocal() as db:
        db.get(AppSettings, 1).embed_model = "old-model"
        db.query(Entry).delete()
        db.add(Entry(
            id="mm1", entry_date="2026-04-01", title="t", content="c",
            embedding=pack_vector(_np.array([0.1], dtype=_np.float32)),
            embedding_model="old-model",
        ))
        db.commit()

    r = c.put("/api/settings", json={"embed_model": "new-model"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("warning") == "embedding_model_mismatch"
    assert body["embedding_mismatch"]["old_model"] == "old-model"
    assert body["embedding_mismatch"]["new_model"] == "new-model"
    assert body["embedding_mismatch"]["affected_entries"] == 1

    # model actually changed in DB (warning is informational, not blocking)
    with SessionLocal() as db:
        assert db.get(AppSettings, 1).embed_model == "new-model"


def test_settings_put_no_warning_when_no_existing_entries():
    c = _auth_client()
    with SessionLocal() as db:
        db.query(Entry).delete()
        db.get(AppSettings, 1).embed_model = "m1"
        db.commit()

    r = c.put("/api/settings", json={"embed_model": "m2"})
    assert r.status_code == 200
    assert "warning" not in r.json()
```

- [ ] **Step 2: Tests laufen lassen — erwartet Fail**

Run: `cd backend && .venv/bin/pytest tests/test_settings_routes.py::test_settings_put_warns_on_embed_model_change_with_existing_entries -v`
Expected: FAIL — `body.get("warning")` ist None.

- [ ] **Step 3: Settings-Route erweitern**

In `backend/app/routes/settings.py`:

1. Import ergänzen:

```python
from sqlalchemy import func, select

from app.models.entry import Entry
```

2. `update_settings` anpassen — vor dem return die Model-Change-Erkennung einfügen:

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
            affected = db.scalar(
                select(func.count()).select_from(Entry).where(
                    Entry.embedding_model.is_not(None),
                    Entry.embedding_model != new_embed_model,
                )
            ) or 0
            if affected > 0:
                mismatch = {
                    "old_model": old_embed_model,
                    "new_model": new_embed_model,
                    "affected_entries": int(affected),
                }
        db.commit()

    resp = {"ok": True}
    if mismatch:
        resp["warning"] = "embedding_model_mismatch"
        resp["embedding_mismatch"] = mismatch
    return resp
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd backend && .venv/bin/pytest tests/test_settings_routes.py -v`
Expected: alle grün (inkl. 2 neue).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/settings.py backend/tests/test_settings_routes.py
git commit -m "feat(settings): warn on embed_model change when entries exist"
```

---

## Task 16: Startup-Lifespan — Backfill starten

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Bestehenden lifespan finden**

Run: `grep -n "lifespan" backend/app/main.py`
Expected: Zeile mit `@asynccontextmanager` oder `async def lifespan(...)`.

- [ ] **Step 2: Backfill-Task im lifespan-Enter starten**

Im bestehenden lifespan-Block **innerhalb des `try:` vor dem `yield`** einfügen:

```python
    import asyncio as _asyncio
    from app.services.embedding_jobs import backfill_missing_embeddings
    _asyncio.create_task(backfill_missing_embeddings())
```

(Der Task läuft im Hintergrund und blockiert den Server-Start nicht.)

- [ ] **Step 3: Smoke-Test der App-Initialisierung**

Run: `cd backend && .venv/bin/python -c "from app.main import app; print('ok')"`
Expected: `ok`, keine Exceptions.

- [ ] **Step 4: Alle Backend-Tests laufen**

Run: `cd backend && .venv/bin/pytest -q`
Expected: alle grün.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(startup): schedule embedding backfill on app lifespan enter"
```

---

## Task 17: Frontend — Search-API-Client

**Files:**
- Create: `frontend/src/lib/search.ts`
- Create: `frontend/tests/unit/search-api.test.ts`

- [ ] **Step 1: Test schreiben**

`frontend/tests/unit/search-api.test.ts`:

```typescript
import { beforeEach, describe, expect, test, vi } from "vitest";
import { searchEntries, getSearchStatus, reindexEmbeddings } from "../../src/lib/search";

describe("search api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    // minimal cookie for CSRF read (bestehendes api<T>()-Pattern liest X-CSRF aus Cookies/Store)
  });

  test("searchEntries posts query and topK", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ results: [], status: "ok" }),
        { status: 200, headers: { "content-type": "application/json" } }
      )
    );
    const r = await searchEntries("regenbogen", 5);
    expect(r.status).toBe("ok");
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/search");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ query: "regenbogen", top_k: 5 });
  });

  test("getSearchStatus does GET", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ total: 1, embedded: 1, pending: 0, current_model: "m", configured: true, indexing: false }),
        { status: 200, headers: { "content-type": "application/json" } }
      )
    );
    const s = await getSearchStatus();
    expect(s.configured).toBe(true);
    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/api/search/status");
  });

  test("reindexEmbeddings does POST", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 202, headers: { "content-type": "application/json" } })
    );
    await reindexEmbeddings();
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/search/reindex");
    expect(call[1].method).toBe("POST");
  });
});
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd frontend && npm test -- search-api.test.ts`
Expected: FAIL mit Modul nicht gefunden.

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
  status: "ok" | "indexing" | "not_configured";
  progress?: { embedded: number; total: number };
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
    body: JSON.stringify({ query, top_k: topK }),
  });
}

export function getSearchStatus(): Promise<SearchStatus> {
  return api<SearchStatus>("/api/search/status", { method: "GET" });
}

export function reindexEmbeddings(): Promise<void> {
  return api<void>("/api/search/reindex", { method: "POST" });
}
```

**Hinweis:** Das bestehende `api<T>()`-Helper fügt CSRF-Header und JSON-Content-Type selbstständig hinzu (siehe `frontend/src/lib/api.ts`). Wenn der Test dort direktes `fetch` erwartet, ggf. `api` mocken statt fetch — schau in `frontend/tests/unit/` nach Pattern.

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd frontend && npm test -- search-api.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/search.ts frontend/tests/unit/search-api.test.ts
git commit -m "feat(frontend): search API client (searchEntries/status/reindex)"
```

---

## Task 18: Frontend — Search-Store

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
    expect(searchStore.results?.[0].entry_id).toBe("e1");
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
});
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd frontend && npm test -- search-store.test.ts`
Expected: FAIL mit Modul nicht gefunden.

- [ ] **Step 3: Store implementieren**

`frontend/src/lib/stores/search.svelte.ts`:

```typescript
import { searchEntries, getSearchStatus, type RerankedResult, type SearchStatus } from "$lib/search";

type Mode = "keyword" | "semantic";

class SearchStore {
  query = $state("");
  mode: Mode = $state("keyword");
  loading = $state(false);
  results: RerankedResult[] | null = $state(null);
  status: SearchStatus | null = $state(null);
  error: string | null = $state(null);

  setMode(m: Mode) {
    this.mode = m;
    this.results = null;
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
      if (resp.status !== "ok") {
        this.status = {
          total: resp.progress?.total ?? 0,
          embedded: resp.progress?.embedded ?? 0,
          pending: 0,
          current_model: null,
          configured: resp.status !== "not_configured",
          indexing: resp.status === "indexing",
        };
      }
    } catch (e: any) {
      this.error = e?.message ?? "Suche fehlgeschlagen";
      this.results = null;
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
    this.status = null;
    this.error = null;
  }
}

export const searchStore = new SearchStore();
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd frontend && npm test -- search-store.test.ts`
Expected: 3 passed.

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
import { describe, expect, test } from "vitest";
import { render, fireEvent, cleanup } from "@testing-library/svelte";
import { afterEach } from "vitest";
import SearchToggle from "../../src/lib/components/SearchToggle.svelte";

afterEach(() => cleanup());

describe("SearchToggle", () => {
  test("renders ARIA switch with current value", () => {
    const { getByRole } = render(SearchToggle, { props: { value: "keyword", onChange: () => {} } });
    const el = getByRole("switch");
    expect(el.getAttribute("aria-checked")).toBe("false");
    expect(el.getAttribute("aria-label")).toMatch(/semantisch/i);
  });

  test("calls onChange when clicked", async () => {
    let called: string | null = null;
    const { getByRole } = render(SearchToggle, {
      props: { value: "keyword", onChange: (v: any) => (called = v) },
    });
    await fireEvent.click(getByRole("switch"));
    expect(called).toBe("semantic");
  });

  test("reflects value=semantic with aria-checked=true", () => {
    const { getByRole } = render(SearchToggle, { props: { value: "semantic", onChange: () => {} } });
    expect(getByRole("switch").getAttribute("aria-checked")).toBe("true");
  });
});
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd frontend && npm test -- search-toggle.test.svelte.ts`
Expected: FAIL mit Modul nicht gefunden.

- [ ] **Step 3: Komponente schreiben**

`frontend/src/lib/components/SearchToggle.svelte`:

```svelte
<script lang="ts">
  type Mode = "keyword" | "semantic";
  interface Props {
    value: Mode;
    onChange: (v: Mode) => void;
  }
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
  <span class="label keyword" class:active={value === "keyword"}>Stichwort</span>
  <span class="label semantic" class:active={value === "semantic"}>Semantisch</span>
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

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

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
  test("renders title, excerpt, score and reason", () => {
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

  test("hides reason line when reason is null", () => {
    const { queryByTestId } = render(SearchResultCard, {
      props: {
        result: { entry_id: "e2", title: "t", excerpt: "e", score: 10, reason: null },
      },
    });
    expect(queryByTestId("reason-line")).toBeNull();
  });
});
```

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd frontend && npm test -- search-result-card.test.svelte.ts`
Expected: FAIL mit Modul nicht gefunden.

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
    font-size: 0.75rem;
    padding: 0.15rem 0.4rem;
    background: var(--accent-soft, #dbeafe);
    color: var(--accent, #2563eb);
    border-radius: 999px;
  }
  .excerpt {
    margin: 0.5rem 0 0.25rem;
    color: var(--muted, #555);
    font-size: 0.9rem;
  }
  .reason {
    margin: 0.25rem 0 0;
    color: var(--muted, #888);
    font-size: 0.8rem;
    font-style: italic;
  }
</style>
```

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd frontend && npm test -- search-result-card.test.svelte.ts`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/SearchResultCard.svelte frontend/tests/unit/search-result-card.test.svelte.ts
git commit -m "feat(frontend): SearchResultCard with score badge + reason line"
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

  test("shows old, new and count", () => {
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

- [ ] **Step 2: Test laufen lassen — erwartet Fail**

Run: `cd frontend && npm test -- model-mismatch-dialog.test.svelte.ts`
Expected: FAIL mit Modul nicht gefunden.

- [ ] **Step 3: Komponente schreiben**

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
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.35);
    display: grid; place-items: center;
    z-index: 1000;
  }
  .dialog {
    background: white; padding: 1.5rem;
    border-radius: 0.5rem;
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

- [ ] **Step 4: Tests laufen lassen — erwartet Pass**

Run: `cd frontend && npm test -- model-mismatch-dialog.test.svelte.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/ModelMismatchDialog.svelte frontend/tests/unit/model-mismatch-dialog.test.svelte.ts
git commit -m "feat(frontend): ModelMismatchDialog with revert/reindex/later actions"
```

---

## Task 22: Frontend — /entries Integration (Such-UI)

**Files:**
- Modify: `frontend/src/routes/entries/+page.svelte`

- [ ] **Step 1: Bestehendes Suchfeld finden**

Run: `grep -n "q = " frontend/src/routes/entries/+page.svelte`
Expected: aktuelles State-Handling des `q`-Parameters.

- [ ] **Step 2: Toggle + Mikrofon-Button + SearchResultList einbauen**

In `frontend/src/routes/entries/+page.svelte`:

1. Imports oben ergänzen:

```svelte
<script lang="ts">
  import { searchStore } from "$lib/stores/search.svelte";
  import SearchToggle from "$lib/components/SearchToggle.svelte";
  import SearchResultCard from "$lib/components/SearchResultCard.svelte";
  import { transcribeAudio } from "$lib/transcribe"; // bestehender Helper von /new
  // ... bestehende Imports
</script>
```

2. Im Template vor/neben dem Suchfeld einfügen:

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

{#if searchStore.mode === "semantic" && searchStore.results}
  <div class="search-results">
    {#if searchStore.results.length === 0}
      <p class="empty">Keine Treffer.</p>
    {:else}
      {#each searchStore.results as r (r.entry_id)}
        <SearchResultCard result={r} />
      {/each}
    {/if}
  </div>
{:else}
  <!-- bestehende EntryList für keyword mode -->
{/if}
```

3. Script-Block ergänzen:

```svelte
<script lang="ts">
  // ... bestehender State
  let recording = $state(false);
  let mediaRecorder: MediaRecorder | null = $state(null);

  async function runSearch() {
    if (searchStore.mode === "semantic") {
      await searchStore.runSearch(searchStore.query);
    } else {
      // bestehender Keyword-Fetch mit q/tags
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

**Hinweis:** Wenn `transcribeAudio` in `/new` inline implementiert statt als Helper ausgelagert ist, baue den Helper in `frontend/src/lib/transcribe.ts` aus dem bestehenden Code heraus — einmalig, DRY. Pattern-Referenz: `grep -n "transcribe" frontend/src/routes/new/+page.svelte`.

- [ ] **Step 3: Manueller Check — npm run check**

Run: `cd frontend && npm run check`
Expected: 0 errors (evtl. Warnings ignorieren).

- [ ] **Step 4: Unit-Tests weiterhin grün**

Run: `cd frontend && npm test`
Expected: alle grün.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/entries/+page.svelte frontend/src/lib/transcribe.ts
git commit -m "feat(entries): add semantic search UI (toggle, mic, result cards)"
```

---

## Task 23: Frontend — Banner-Komponenten für Status-Edge-Cases

**Files:**
- Create: `frontend/src/lib/components/SearchStatusBanner.svelte`
- Modify: `frontend/src/routes/entries/+page.svelte`

- [ ] **Step 1: Komponente schreiben**

`frontend/src/lib/components/SearchStatusBanner.svelte`:

```svelte
<script lang="ts">
  import type { SearchStatus, SemanticSearchResponse } from "$lib/search";
  interface Props {
    status: SearchStatus | null;
    result: SemanticSearchResponse | null;
  }
  let { status, result }: Props = $props();
</script>

{#if result?.status === "not_configured" || status?.configured === false}
  <div class="banner warn">
    Semantische Suche ist nicht konfiguriert.
    <a href="/settings">Einstellungen öffnen</a>
  </div>
{:else if result?.status === "indexing"}
  <div class="banner info">
    Index wird gebaut … {result.progress?.embedded ?? 0} von {result.progress?.total ?? 0}
  </div>
{/if}

<style>
  .banner { padding: 0.75rem 1rem; border-radius: 0.375rem; margin-bottom: 0.75rem; }
  .banner.warn { background: #fef3c7; color: #92400e; }
  .banner.info { background: #dbeafe; color: #1e40af; }
  a { color: inherit; text-decoration: underline; }
</style>
```

- [ ] **Step 2: In /entries einbinden**

In `frontend/src/routes/entries/+page.svelte` unter der `search-row` einfügen:

```svelte
<SearchStatusBanner status={searchStore.status} result={...} />
```

(Du brauchst den Raw-Response aus der letzten `runSearch` — erweitere den Store um ein `lastResponse`-Feld oder leite `status` aus dem Store ab.)

Dafür im Store (`search.svelte.ts`) ein Feld `lastResponse` ergänzen:

```typescript
lastResponse: SemanticSearchResponse | null = $state(null);
// in runSearch:
this.lastResponse = resp;
// in reset:
this.lastResponse = null;
```

Dann im Template:

```svelte
<SearchStatusBanner status={searchStore.status} result={searchStore.lastResponse} />
```

- [ ] **Step 3: Smoke-Check**

Run: `cd frontend && npm run check && npm test`
Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/SearchStatusBanner.svelte frontend/src/lib/stores/search.svelte.ts frontend/src/routes/entries/+page.svelte
git commit -m "feat(entries): banner for not_configured and indexing states"
```

---

## Task 24: Frontend — /settings Embed-Status + Reindex-Button

**Files:**
- Modify: `frontend/src/routes/settings/+page.svelte`

- [ ] **Step 1: Embed-Block um Status + Reindex erweitern**

Im Settings-Template einen Block im Embed-Abschnitt einfügen:

```svelte
<script lang="ts">
  import { getSearchStatus, reindexEmbeddings, type SearchStatus } from "$lib/search";
  import ModelMismatchDialog from "$lib/components/ModelMismatchDialog.svelte";

  let embedStatus: SearchStatus | null = $state(null);
  let mismatch: any = $state(null);

  async function loadStatus() {
    try {
      embedStatus = await getSearchStatus();
    } catch {}
  }

  async function triggerReindex() {
    if (!confirm(`Alle ${embedStatus?.total ?? 0} Einträge werden neu indexiert.`)) return;
    await reindexEmbeddings();
    await loadStatus();
  }

  onMount(loadStatus);
</script>

<section class="embed-status">
  <h3>Index-Status</h3>
  {#if embedStatus}
    <p>{embedStatus.embedded} von {embedStatus.total} Einträgen indexiert (Modell: {embedStatus.current_model ?? "–"})</p>
    <button type="button" onclick={triggerReindex}>Jetzt neu indexieren</button>
  {/if}
</section>
```

- [ ] **Step 2: Settings-PUT-Response auf warning prüfen**

Wo aktuell die Settings gespeichert werden (z.B. `savePayload` oder ähnlich), das Response-Objekt inspizieren:

```typescript
const resp = await api("/api/settings", { method: "PUT", body: JSON.stringify(payload) });
if (resp?.warning === "embedding_model_mismatch") {
  mismatch = resp.embedding_mismatch;
}
```

- [ ] **Step 3: Dialog einbinden**

```svelte
<ModelMismatchDialog
  open={mismatch !== null}
  mismatch={mismatch}
  onRevert={async () => {
    await api("/api/settings", { method: "PUT", body: JSON.stringify({ embed_model: mismatch.old_model }) });
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

- [ ] **Step 4: Smoke-Check**

Run: `cd frontend && npm run check && npm test`
Expected: keine Fehler.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/settings/+page.svelte
git commit -m "feat(settings): embed index status + reindex button + model-mismatch dialog"
```

---

## Task 25: Playwright-Skeleton für Semantische Suche

**Files:**
- Create: `frontend/tests/e2e/semantic-search.spec.ts`

- [ ] **Step 1: E2E-Test schreiben (E2E_LIVE-gated, Skeleton-Pattern)**

`frontend/tests/e2e/semantic-search.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

const LIVE = !!process.env.E2E_LIVE;

test.describe("semantic search", () => {
  test.skip(!LIVE, "E2E_LIVE not set — running offline skeleton");

  test("toggle to semantic, run query, see results", async ({ page }) => {
    await page.goto("/entries");
    // Login path if needed — mirror existing entry-crud.spec pattern
    await page.getByRole("switch", { name: /semantisch/i }).click();
    await page.getByPlaceholder(/ganzen Sätzen/).fill("Hey, habe ich mal von Regenbögen geträumt?");
    await page.getByRole("button", { name: /Suchen/ }).click();
    await expect(page.locator(".card").first()).toBeVisible({ timeout: 15000 });
  });

  test("voice path: mic button → STT → query filled", async ({ page }) => {
    await page.goto("/entries");
    await page.getByRole("switch", { name: /semantisch/i }).click();
    // Playwright microphone injection requires browser context permissions
    // — leave as a skipped hook; full implementation in E2E_LIVE run.
    test.skip(true, "mic injection only in E2E_LIVE with manual setup");
  });
});
```

- [ ] **Step 2: Playwright-Lauf ohne E2E_LIVE — Skeleton greift**

Run: `cd frontend && npx playwright test tests/e2e/semantic-search.spec.ts`
Expected: 2 skipped (0 failed).

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/semantic-search.spec.ts
git commit -m "test(e2e): Playwright skeleton for semantic search (E2E_LIVE-gated)"
```

---

## Task 26: End-to-End-Manual-Test + Roadmap-Update

**Files:**
- Modify: `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md`

- [ ] **Step 1: Lokalen Stack starten**

Run: `docker compose -f deploy/docker-compose.yml down && docker compose -f deploy/docker-compose.yml up -d --build`
Expected: alle drei Container laufen (`docker ps` zeigt caddy, backend, frontend).

- [ ] **Step 2: Manuelle Smoke-Pfade durchgehen**

Im Browser:

1. Login → Einträge existieren (ggf. 2-3 Test-Einträge schreiben).
2. /settings → Embed-Feld ausfüllen (`text-embedding-3-small` + API-Key) → speichern.
3. Warte 5-10 s, /settings → Status-Block zeigt `N von N Einträgen indexiert`.
4. /entries → Toggle auf Semantisch → tippe „Traum mit Regenbogen" → Klick Suchen → Results erscheinen mit Reason.
5. Mikrofon-Button: aufnehmen, diktieren, stoppen → Query wird gefüllt + Suche läuft.
6. /settings → embed_model auf anderen Wert ändern → Modalmitschrift-Dialog erscheint → "Später entscheiden" → Banner sichtbar → nochmal öffnen → "Neu indexieren" → Reindex-Lauf.
7. Einen Eintrag editieren (Content ändern) → nach 2 s sollte er wieder in Semantik-Suche auftauchen.

- [ ] **Step 3: Backend-Tests komplett**

Run: `cd backend && .venv/bin/pytest -q`
Expected: alle grün, keine neuen Warnings.

- [ ] **Step 4: Frontend-Tests komplett**

Run: `cd frontend && npm test && npm run check`
Expected: alle grün.

- [ ] **Step 5: Roadmap aktualisieren**

Öffne `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md` und:

- Entferne den „In Arbeit"-Block für Phase 2.
- Füge unter „Erledigt" einen neuen Abschnitt ein:

```markdown
### Phase 2 Semantische Suche (`v0.3.0-search`)
- Backend: embedding/embedding_model/embedding_updated_at Spalten auf entries + embed_dimensions auf settings (Alembic). numpy-Dependency. services/embeddings.py (pack/unpack/cosine/build_entry_text/embed_text mit 502-Mapping), services/search.py (intent-extract, LLM-rerank mit Cosine-Fallback, semantic_search), services/embedding_jobs.py (async embed-on-save mit Delete-Race-Schutz, Startup-Backfill, Reindex mit asyncio-Lock). Neue Routen POST /api/search + GET /api/search/status + POST /api/search/reindex (Rate-Limits 30/min und 1/min, CSRF + Session). Settings-PUT meldet `embedding_model_mismatch` mit affected-count. Entry-Create/Update invalidiert Embedding bei Content-Änderung und schedulet BackgroundTask. Alle neuen Code-Pfade getestet (respx-Mocks).
- Frontend: search.ts API-Client + search.svelte.ts Store, SearchToggle (ARIA switch), SearchResultCard (Score-Badge + Reason), SearchStatusBanner (not_configured + indexing), ModelMismatchDialog mit Revert/Reindex/Later. /entries-Seite mit Toggle + Voice-Input (Reuse der transcribe-Pipeline) + Result-Rendering. /settings-Seite mit Index-Status, Reindex-Button, Modellwechsel-Dialog-Integration.
- E2E-Skeleton für Query-Pfad + Voice-Pfad (E2E_LIVE-gated).
```

- Aktualisiere `Letzte Aktualisierung dieser Datei:`-Zeile.

- [ ] **Step 6: Commit**

```bash
git add /home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md 2>/dev/null || true
git commit --allow-empty -m "chore: phase 2 semantic search done (v0.3.0-search)"
git tag v0.3.0-search
```

(Der explizite `allow-empty` ist nur ein Safety-Net falls keine projekt-internen Dateien mit im Commit stecken; in der Praxis wird das Tag einfach das letzte Commit markieren.)

---

## Self-Review-Notes (vom Plan-Autor)

- **Spec-Coverage:** Jeder Abschnitt der Spec (Datenmodell, Backend-Services, Routen, Frontend-Komponenten, Settings-Flow, Error-Handling, Testing) hat mindestens einen zugeordneten Task. Der Modellwechsel-Flow ist auf Tasks 15, 21, 24 verteilt.
- **Placeholder-Scan:** Keine „TBD"/„TODO"/„implement later"-Stellen. Alle `grep`-Hinweise in Tasks 12, 16, 22 sind zielgerichtet (Pattern-Lookup für bestehende Konventionen).
- **Type-Konsistenz:** `RerankedResult` (Task 7) und `SemanticSearchResponse` (Task 8) werden in Frontend-Types (Task 17) gespiegelt. `embed_entry_async` / `backfill_missing_embeddings` / `reindex_all` sind quer durch die Tasks konsistent benannt.
- **Frontend-Test-Konvention:** `@testing-library/svelte` braucht laut Roadmap-Known-Caveats `resolve.conditions: ["browser"]` in `vitest.config.ts` und `cleanup()` in `afterEach` — beides ist im bestehenden Setup schon vorhanden (TTS-Tests nutzen es), die neuen Svelte-Tests setzen `afterEach(cleanup)` entsprechend.
- **Offene Pattern-Lookups** (bewusst delegiert, statt hier geraten): slowapi-Request-Parameter in Task 12/14 (Pattern aus `/api/tts`), `transcribeAudio`-Extraktion aus `/new` in Task 22, CSRF-Extraktions-Pattern im Settings-PUT in Task 24. Diese sind in-Task als `grep`-Befehle dokumentiert — keine Blocker, aber Verifikation nötig.
