# U1 — Embedding-Tabelle separieren (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die drei Embedding-Spalten (`embedding`, `embedding_model`, `embedding_updated_at`) von `entries` in eine dedizierte `entry_embeddings`-Tabelle auslagern, um `/api/entries`-SELECTs zu entlasten und mehrere Modelle pro Entry architektonisch zu ermöglichen.

**Architecture:** Neue Tabelle `entry_embeddings(entry_id, model, dim, vector BLOB, created_at)` mit Composite-PK `(entry_id, model)` und `ON DELETE CASCADE`. Additive Migration: Tabelle zuerst anlegen (ohne Daten-Move), Konsumenten schrittweise umstellen, dann Daten kopieren und alte Spalten droppen. Jeder Task ist ein Commit; Tests werden pro Task synchron zum Produktionscode umgestellt. Keine API-Änderungen.

**Tech Stack:** FastAPI + SQLAlchemy 2 (`Mapped`/`mapped_column`) + Alembic + SQLCipher + pytest. numpy für Vector-Ops.

**Worktree:** `/home/julian/Projekte/journalAI/.worktrees/u1-embedding-table` (Branch `feature/u1-embedding-table`)

**Pytest-Kommando im Worktree:**
```bash
cd /home/julian/Projekte/journalAI/.worktrees/u1-embedding-table/backend
/home/julian/Projekte/journalAI/backend/.venv/bin/pytest -q
```
(Die main-venv wird wiederverwendet — libsqlcipher-dev ist dort bereits installiert.)

---

## Task 1: Additive Alembic-Migration — `entry_embeddings`-Tabelle anlegen

**Files:**
- Create: `backend/alembic/versions/<new_id>_add_entry_embeddings_table.py`
- Test: (Migration-Roundtrip über `Base.metadata.create_all` in Task 2)

- [ ] **Step 1: Neue Alembic-Revision generieren**

```bash
cd backend && /home/julian/Projekte/journalAI/backend/.venv/bin/alembic revision -m "add entry_embeddings table"
```

Notiere die generierte Revision-ID.

- [ ] **Step 2: Migration-Inhalt schreiben**

Inhalt der neuen Datei (down_revision = `'6816f8ae8a20'`):

```python
"""add entry_embeddings table

Revision ID: <generated>
Revises: 6816f8ae8a20
Create Date: 2026-04-17 ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<generated>'
down_revision: Union[str, Sequence[str], None] = '6816f8ae8a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entry_embeddings",
        sa.Column("entry_id", sa.String(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("entry_id", "model"),
    )


def downgrade() -> None:
    op.drop_table("entry_embeddings")
```

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(u1): add entry_embeddings table migration"
```

---

## Task 2: SQLAlchemy-Modell `EntryEmbedding`

**Files:**
- Create: `backend/app/models/entry_embedding.py`
- Modify: `backend/app/models/__init__.py` (Import hinzufügen, damit `Base.metadata` das Modell kennt)
- Test: `backend/tests/test_models.py` (vorhanden — neue Testfunktion anhängen)

- [ ] **Step 1: Failing Test schreiben**

Anhängen an `backend/tests/test_models.py`:

```python
def test_entry_embedding_roundtrip():
    from datetime import date
    from app.models.entry import Entry
    from app.models.entry_embedding import EntryEmbedding
    from app.db import Base, SessionLocal, engine

    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.query(EntryEmbedding).delete()
        db.query(Entry).delete()
        db.add(Entry(id="ee1", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.add(EntryEmbedding(entry_id="ee1", model="m1", dim=3, vector=b"\x00" * 12))
        db.commit()

        row = db.get(EntryEmbedding, ("ee1", "m1"))
        assert row is not None
        assert row.dim == 3
        assert len(row.vector) == 12

        # Cascade delete
        db.delete(db.get(Entry, "ee1"))
        db.commit()
        assert db.get(EntryEmbedding, ("ee1", "m1")) is None
```

- [ ] **Step 2: Verify FAIL**

Run: `pytest tests/test_models.py::test_entry_embedding_roundtrip -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.models.entry_embedding'`).

- [ ] **Step 3: Modell implementieren**

`backend/app/models/entry_embedding.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class EntryEmbedding(Base):
    __tablename__ = "entry_embeddings"

    entry_id: Mapped[str] = mapped_column(
        String, ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String, primary_key=True)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    entry = relationship("Entry", back_populates="embeddings")
```

Ergänze `backend/app/models/entry.py` am Ende (nach der `tags`-Relationship):

```python
    embeddings: Mapped[list["EntryEmbedding"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )
```

Ergänze `backend/app/models/__init__.py`:

```python
from app.models.entry_embedding import EntryEmbedding  # noqa: F401
```

- [ ] **Step 4: Verify PASS**

Run: `pytest tests/test_models.py::test_entry_embedding_roundtrip -v`
Expected: PASS.

- [ ] **Step 5: Komplett-Run**

Run: `pytest -q`
Expected: 152 passed (151 bisherige + 1 neue).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/entry_embedding.py backend/app/models/entry.py backend/app/models/__init__.py backend/tests/test_models.py
git commit -m "feat(u1): add EntryEmbedding SQLAlchemy model"
```

---

## Task 3: Helper in `embeddings.py` — load/save/delete

**Files:**
- Modify: `backend/app/services/embeddings.py:1-84` (drei neue Funktionen anhängen)
- Test: `backend/tests/test_embeddings_service.py` (neue Testfunktionen anhängen)

- [ ] **Step 1: Failing Tests schreiben**

Anhängen an `backend/tests/test_embeddings_service.py`:

```python
def test_save_and_load_embedding_vector():
    from datetime import date
    import numpy as np
    from app.db import Base, SessionLocal, engine
    from app.models.entry import Entry
    from app.services.embeddings import (
        load_embedding_vector,
        save_embedding_vector,
    )

    engine.dispose()
    Base.metadata.create_all(engine)
    vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    with SessionLocal() as db:
        db.query(Entry).delete()
        db.add(Entry(id="e1", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()
        save_embedding_vector(db, "e1", "m1", vec)
        db.commit()

    with SessionLocal() as db:
        got = load_embedding_vector(db, "e1", "m1")
        assert got is not None
        assert np.allclose(got, vec)
        assert load_embedding_vector(db, "e1", "m-other") is None


def test_save_embedding_upserts_on_same_model():
    from datetime import date
    import numpy as np
    from app.db import Base, SessionLocal, engine
    from app.models.entry import Entry
    from app.models.entry_embedding import EntryEmbedding
    from app.services.embeddings import save_embedding_vector

    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.query(Entry).delete()
        db.add(Entry(id="e2", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()
        save_embedding_vector(db, "e2", "m1", np.array([1.0, 0.0], dtype=np.float32))
        save_embedding_vector(db, "e2", "m1", np.array([0.0, 1.0], dtype=np.float32))
        db.commit()

    with SessionLocal() as db:
        rows = db.query(EntryEmbedding).filter_by(entry_id="e2").all()
        assert len(rows) == 1
        assert rows[0].dim == 2


def test_delete_embeddings_for_entry_removes_all_models():
    from datetime import date
    import numpy as np
    from app.db import Base, SessionLocal, engine
    from app.models.entry import Entry
    from app.models.entry_embedding import EntryEmbedding
    from app.services.embeddings import (
        delete_embeddings_for_entry,
        save_embedding_vector,
    )

    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.query(Entry).delete()
        db.add(Entry(id="e3", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.commit()
        save_embedding_vector(db, "e3", "m1", np.array([1.0], dtype=np.float32))
        save_embedding_vector(db, "e3", "m2", np.array([1.0, 2.0], dtype=np.float32))
        db.commit()
        delete_embeddings_for_entry(db, "e3")
        db.commit()

    with SessionLocal() as db:
        assert db.query(EntryEmbedding).filter_by(entry_id="e3").count() == 0
```

- [ ] **Step 2: Verify FAIL**

Run: `pytest tests/test_embeddings_service.py -k "save_and_load or upserts or delete_embeddings_for_entry" -v`
Expected: FAIL (ImportError auf `load_embedding_vector` etc.).

- [ ] **Step 3: Helper implementieren**

Anhängen an `backend/app/services/embeddings.py`:

```python
def load_embedding_vector(db, entry_id: str, model: str) -> np.ndarray | None:
    """Return the float32 vector for (entry_id, model), or None if absent."""
    from app.models.entry_embedding import EntryEmbedding

    row = db.get(EntryEmbedding, (entry_id, model))
    if row is None:
        return None
    return unpack_vector(row.vector)


def save_embedding_vector(db, entry_id: str, model: str, vec: np.ndarray) -> None:
    """Upsert a vector for (entry_id, model). Does NOT commit."""
    from app.models.entry_embedding import EntryEmbedding

    blob = pack_vector(vec)
    dim = int(vec.shape[0])
    row = db.get(EntryEmbedding, (entry_id, model))
    if row is None:
        db.add(EntryEmbedding(entry_id=entry_id, model=model, dim=dim, vector=blob))
    else:
        row.vector = blob
        row.dim = dim


def delete_embeddings_for_entry(db, entry_id: str) -> None:
    """Remove all embedding rows for an entry (all models). Does NOT commit."""
    from app.models.entry_embedding import EntryEmbedding

    db.query(EntryEmbedding).filter_by(entry_id=entry_id).delete(synchronize_session=False)
```

- [ ] **Step 4: Verify PASS**

Run: `pytest tests/test_embeddings_service.py -v`
Expected: All tests pass (existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/embeddings.py backend/tests/test_embeddings_service.py
git commit -m "feat(u1): add load/save/delete helpers for entry_embeddings"
```

---

## Task 4: `embedding_jobs.py` umstellen auf neue Tabelle

**Files:**
- Modify: `backend/app/services/embedding_jobs.py:40-98` (embed_entry_async), `:139-166` (_do_backfill), `:190-204` (_do_reindex)
- Test: `backend/tests/test_embedding_jobs.py` (alle Stellen mit `Entry(embedding=...)` umstellen auf `EntryEmbedding`-Inserts)

- [ ] **Step 1: Failing Tests identifizieren / anpassen**

`backend/tests/test_embedding_jobs.py` komplett überfliegen. Jede Stelle, die `Entry(embedding=...)` oder `e.embedding = ...` benutzt, wird ersetzt durch einen expliziten `EntryEmbedding`-Insert via `save_embedding_vector`-Helper. Assertions `assert e.embedding is None` → `assert db.get(EntryEmbedding, (entry_id, model)) is None`.

Konkret (grep zuerst):

```bash
grep -n "embedding" tests/test_embedding_jobs.py
```

Für jede Fundstelle: Umbau nach Pattern
- Before: `Entry(..., embedding=pack_vector(v), embedding_model="m1")`
- After: `Entry(...)` + danach `save_embedding_vector(db, id, "m1", v); db.commit()`

- [ ] **Step 2: Verify FAIL**

Run: `pytest tests/test_embedding_jobs.py -v`
Expected: Mehrere Failures — Test erwartet neues Verhalten, Produktionscode schreibt aber noch in alte Spalten.

- [ ] **Step 3: `embed_entry_async` umstellen**

In `backend/app/services/embedding_jobs.py`, Funktion `embed_entry_async` (ab Zeile ~40): Den abschließenden Write-Block durch Helper-Call ersetzen.

Ersetze:
```python
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

Durch:
```python
    with SessionLocal() as db:
        e = db.get(Entry, entry_id)
        if e is None:
            return  # deleted between embed + write
        save_embedding_vector(db, entry_id, resolved_model, vec)
        s = db.get(AppSettings, 1)
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

Importe ergänzen:
```python
from app.services.embeddings import (
    ProviderRateLimited,
    build_entry_text,
    embed_text,
    save_embedding_vector,
)
```

(`pack_vector`-Import fällt weg falls ungenutzt.)

- [ ] **Step 4: `_do_backfill` umstellen**

Ersetze die `select(Entry.id).where(or_(...))`-Query durch LEFT-JOIN-Variante:

```python
async def _do_backfill() -> None:
    current = _current_embed_model()
    if not current:
        log.info("_do_backfill: no embed_model configured, skipping")
        return

    from app.models.entry_embedding import EntryEmbedding

    with SessionLocal() as db:
        # Entries ohne Row für current model in entry_embeddings
        subq = (
            select(EntryEmbedding.entry_id)
            .where(EntryEmbedding.model == current)
        )
        ids = db.execute(
            select(Entry.id)
            .where(Entry.id.notin_(subq))
            .order_by(Entry.updated_at.desc())
        ).scalars().all()

    log.info("_do_backfill: %d entries pending for model=%s", len(ids), current)
    for eid in ids:
        await _embed_one_with_backoff(eid)
        await asyncio.sleep(BACKFILL_THROTTLE_SECONDS)
```

Der `or_`-Import kann raus.

- [ ] **Step 5: `_do_reindex` umstellen**

Ersetze den Block:
```python
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
```

Durch:
```python
    from app.models.entry_embedding import EntryEmbedding

    with SessionLocal() as db:
        db.query(EntryEmbedding).delete(synchronize_session=False)
        db.commit()
    await _do_backfill()
```

- [ ] **Step 6: Verify PASS**

Run: `pytest tests/test_embedding_jobs.py -v`
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/embedding_jobs.py backend/tests/test_embedding_jobs.py
git commit -m "feat(u1): route embedding_jobs through entry_embeddings table"
```

---

## Task 5: `search.py` umstellen auf JOIN

**Files:**
- Modify: `backend/app/services/search.py:155-213` (semantic_search)
- Test: `backend/tests/test_search_service.py` (Inserts umstellen)

- [ ] **Step 1: Tests anpassen**

In `backend/tests/test_search_service.py` jede `Entry(embedding=...)`-Stelle auf separate `EntryEmbedding`-Inserts via `save_embedding_vector` umstellen (gleiches Pattern wie Task 4).

- [ ] **Step 2: Verify FAIL**

Run: `pytest tests/test_search_service.py -v`
Expected: Tests schlagen fehl (Produktionscode liest noch aus `Entry.embedding`, Testdaten liegen aber jetzt in `entry_embeddings`).

- [ ] **Step 3: `semantic_search` umstellen**

In `backend/app/services/search.py` — ersetze den SELECT-Block (ab Zeile ~164):

```python
    with SessionLocal() as db:
        rows = db.execute(
            select(Entry).where(
                Entry.embedding.is_not(None),
                Entry.embedding_model == current_model,
            )
        ).scalars().all()
        total_count = int(db.scalar(select(func.count()).select_from(Entry)) or 0)
        embedded_count = len(rows)
```

Durch:

```python
    from app.models.entry_embedding import EntryEmbedding

    with SessionLocal() as db:
        rows_with_vec = db.execute(
            select(Entry, EntryEmbedding.vector)
            .join(EntryEmbedding, EntryEmbedding.entry_id == Entry.id)
            .where(EntryEmbedding.model == current_model)
        ).all()
        total_count = int(db.scalar(select(func.count()).select_from(Entry)) or 0)
        embedded_count = len(rows_with_vec)
```

Ersetze dann die Dimension-Guard-Schleife (Zeilen ~187-198):

```python
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
```

Durch:

```python
    candidates = []
    vectors = []
    dropped = 0
    for e, blob in rows_with_vec:
        v = unpack_vector(blob)
        if v.shape[0] == query_vec.shape[0]:
            candidates.append(e)
            vectors.append(v)
        else:
            dropped += 1
```

Die `if not rows:`-Zeile wird zu `if not rows_with_vec:`.

- [ ] **Step 4: Verify PASS**

Run: `pytest tests/test_search_service.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search.py backend/tests/test_search_service.py
git commit -m "feat(u1): semantic_search reads vectors via JOIN on entry_embeddings"
```

---

## Task 6: `/api/search/status` umstellen

**Files:**
- Modify: `backend/app/routes/search.py:39-57` (search_status)
- Test: `backend/tests/test_search_routes.py` (Testdaten umstellen)

- [ ] **Step 1: Tests anpassen**

Jede `Entry(embedding=...)`-Stelle in `test_search_routes.py` → `save_embedding_vector`-Helper.

- [ ] **Step 2: Verify FAIL**

Run: `pytest tests/test_search_routes.py -v`
Expected: Failures.

- [ ] **Step 3: Status-Endpoint umstellen**

In `backend/app/routes/search.py`:

```python
@router.get("/status")
async def search_status() -> dict:
    from app.models.entry_embedding import EntryEmbedding

    current = resolved_model("embed")
    with SessionLocal() as db:
        total = int(db.scalar(select(func.count()).select_from(Entry)) or 0)
        if current:
            embedded = int(db.scalar(
                select(func.count())
                .select_from(EntryEmbedding)
                .where(EntryEmbedding.model == current)
            ) or 0)
        else:
            embedded = 0
    return {
        "total": total,
        "embedded": embedded,
        "pending": total - embedded,
        "current_model": current,
        "configured": bool(current),
        "indexing": is_job_running(),
    }
```

- [ ] **Step 4: Verify PASS**

Run: `pytest tests/test_search_routes.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/search.py backend/tests/test_search_routes.py
git commit -m "feat(u1): /api/search/status counts via entry_embeddings"
```

---

## Task 7: `entries.py`-Invalidation umstellen auf DELETE

**Files:**
- Modify: `backend/app/routes/entries.py:113-144` (update_entry)
- Test: `backend/tests/test_entries_embedding.py` (alle Stellen umstellen)

- [ ] **Step 1: Tests anpassen**

In `backend/tests/test_entries_embedding.py`:
- `Entry(..., embedding=pack_vector(...), embedding_model="m1")` → `Entry(...)` + `save_embedding_vector(db, id, "m1", vec)` + `db.commit()`
- `assert e.embedding is None` → `assert db.get(EntryEmbedding, (id, "m1")) is None`
- `assert e.embedding is not None` / `assert e.embedding_model == "m1"` → `assert db.get(EntryEmbedding, (id, "m1")) is not None`

- [ ] **Step 2: Verify FAIL**

Run: `pytest tests/test_entries_embedding.py -v`
Expected: Failures.

- [ ] **Step 3: `update_entry` umstellen**

In `backend/app/routes/entries.py`, Block:
```python
        if text_changed:
            e.embedding = None
            e.embedding_model = None
            e.embedding_updated_at = None
```

Ersetzen durch:
```python
        if text_changed:
            from app.services.embeddings import delete_embeddings_for_entry
            delete_embeddings_for_entry(db, eid)
```

- [ ] **Step 4: Verify PASS**

Run: `pytest tests/test_entries_embedding.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/entries.py backend/tests/test_entries_embedding.py
git commit -m "feat(u1): invalidate embeddings via DELETE on entry update"
```

---

## Task 8: Alembic-Migration — Daten-Move + alte Spalten droppen

**Files:**
- Create: `backend/alembic/versions/<new_id>_drop_entry_embedding_columns.py`
- Test: (Smoke-Test über volle Testsuite in Task 9)

- [ ] **Step 1: Neue Revision generieren**

```bash
cd backend && /home/julian/Projekte/journalAI/backend/.venv/bin/alembic revision -m "move embeddings to entry_embeddings and drop old columns"
```

- [ ] **Step 2: Migration-Inhalt schreiben**

Die `down_revision` ist die ID aus Task 1.

```python
"""move embeddings to entry_embeddings and drop old columns

Revision ID: <generated>
Revises: <task1 id>
Create Date: 2026-04-17 ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<generated>'
down_revision: Union[str, Sequence[str], None] = '<task1 id>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Copy any existing vectors into entry_embeddings. dim is derived from
    # blob length / 4 (float32). Rows with NULL embedding or NULL model are skipped.
    op.execute(
        """
        INSERT INTO entry_embeddings (entry_id, model, dim, vector, created_at)
        SELECT
            id,
            embedding_model,
            CAST(LENGTH(embedding) / 4 AS INTEGER),
            embedding,
            COALESCE(embedding_updated_at, CURRENT_TIMESTAMP)
        FROM entries
        WHERE embedding IS NOT NULL AND embedding_model IS NOT NULL
        """
    )

    with op.batch_alter_table("entries") as batch:
        batch.drop_column("embedding_updated_at")
        batch.drop_column("embedding_model")
        batch.drop_column("embedding")


def downgrade() -> None:
    with op.batch_alter_table("entries") as batch:
        batch.add_column(sa.Column("embedding", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("embedding_model", sa.String(), nullable=True))
        batch.add_column(sa.Column("embedding_updated_at", sa.DateTime(), nullable=True))

    # Best-effort restore: pick the newest row per entry. If multiple models
    # coexist (new architecture feature), only the newest is preserved on downgrade.
    op.execute(
        """
        UPDATE entries
        SET
            embedding = (
                SELECT vector FROM entry_embeddings
                WHERE entry_embeddings.entry_id = entries.id
                ORDER BY created_at DESC LIMIT 1
            ),
            embedding_model = (
                SELECT model FROM entry_embeddings
                WHERE entry_embeddings.entry_id = entries.id
                ORDER BY created_at DESC LIMIT 1
            ),
            embedding_updated_at = (
                SELECT created_at FROM entry_embeddings
                WHERE entry_embeddings.entry_id = entries.id
                ORDER BY created_at DESC LIMIT 1
            )
        WHERE EXISTS (
            SELECT 1 FROM entry_embeddings WHERE entry_embeddings.entry_id = entries.id
        )
        """
    )
```

`batch_alter_table` ist für SQLite nötig (kein natives DROP COLUMN in altem SQLite; SQLCipher folgt SQLite-Semantik).

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(u1): migrate embedding columns to entry_embeddings and drop old"
```

---

## Task 9: Entry-Modell — alte Spalten entfernen

**Files:**
- Modify: `backend/app/models/entry.py:18-20` (drei Zeilen löschen)
- Modify: `backend/app/services/embeddings.py` — obsoleter Import `utc_now` o. ä.? (prüfen)

- [ ] **Step 1: Spalten entfernen**

In `backend/app/models/entry.py` die drei Zeilen entfernen:

```python
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
```

Entferne auch den `LargeBinary`-Import, falls er nur dafür importiert war:

```bash
grep -n LargeBinary backend/app/models/entry.py
```

Falls nur eine Stelle: Import bereinigen.

- [ ] **Step 2: Alle Verbraucher auf `utc_now`-Schleife in `embed_entry_async` prüfen**

In `backend/app/services/embedding_jobs.py` — der `utc_now`-Import bleibt nur nötig, wenn anderswo verwendet. Falls nicht, entfernen:

```bash
grep -n utc_now backend/app/services/embedding_jobs.py
```

- [ ] **Step 3: Volle Testsuite**

Run: `pytest -q`
Expected: Alle Tests grün. Falls irgendwo noch eine Referenz auf `e.embedding` o. ä. übersehen wurde: Fehler jetzt mit klarer Meldung.

Falls Fails: in den Fail-Traces die Stelle lokalisieren, umstellen, wiederholen. Typischer Kandidat: conftest.py oder vergessener Test.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/entry.py backend/app/services/embedding_jobs.py
git commit -m "feat(u1): remove legacy embedding columns from Entry model"
```

---

## Task 10: End-to-End-Smoke + Perf-Spot-Check

**Files:**
- (nur Ausführung, keine Änderungen)

- [ ] **Step 1: Komplett-Testlauf**

```bash
cd /home/julian/Projekte/journalAI/.worktrees/u1-embedding-table/backend
/home/julian/Projekte/journalAI/backend/.venv/bin/pytest -q
```

Expected: Mindestens 154 passed (151 Baseline + 3 neue aus Task 3, ggf. weitere durch Test 2). Falls Regression: fix und commit vor Merge.

- [ ] **Step 2: Perf-Spot-Check**

Minimaler Sanity-Check, dass `/api/entries`-SELECT nicht mehr die Vektoren lädt:

```bash
/home/julian/Projekte/journalAI/backend/.venv/bin/python - <<'EOF'
from datetime import date
import time
import numpy as np
from app.db import Base, SessionLocal, engine
from app.models.entry import Entry
from app.services.embeddings import save_embedding_vector

engine.dispose()
Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.query(Entry).delete()
    for i in range(200):
        db.add(Entry(id=f"perf{i}", entry_date=date(2026, 4, 1),
                     title=f"t{i}", content="x" * 500))
    db.commit()
    vec = np.random.rand(1024).astype(np.float32)
    for i in range(200):
        save_embedding_vector(db, f"perf{i}", "m1", vec)
    db.commit()

with SessionLocal() as db:
    t0 = time.perf_counter()
    rows = db.query(Entry).all()
    for r in rows:
        _ = r.title  # force attribute access
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"SELECT 200 entries: {elapsed:.1f} ms")
    assert not hasattr(rows[0], "embedding"), "embedding attribute should be gone"

    db.query(Entry).delete()
    db.commit()
EOF
```

Erwartung: SELECT < 50 ms auf normaler Hardware (vor U1 typisch 100-300 ms bei 1024-dim-Vektoren inline).

- [ ] **Step 3: Roadmap-Update (nicht gitted — liegt außerhalb des Repos)**

In `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md`:
- Checkbox `U1` von `[ ]` auf `[x]`
- Neuen Stichpunkt in „✅ Erledigt" ergänzen (inkl. Commit-Hashes aller Tasks)
- Datum oben auf 2026-04-17 aktualisieren
- **Kein git commit** — die Datei ist Teil des Claude-Memory-Systems außerhalb des Repos.

- [ ] **Step 4: Merge-Check**

```bash
cd /home/julian/Projekte/journalAI
git checkout main
git log main..feature/u1-embedding-table --oneline
```

Wenn Output = die ~8 Task-Commits + 0 weitere: saubere Historie.

- [ ] **Step 5: Finale Pipeline: finishing-a-development-branch Skill**

Danach: `superpowers:finishing-a-development-branch` Skill für die Merge-/PR-Entscheidung.

---

## Open Risks / Notes

- **SQLCipher + batch_alter_table:** SQLite-Mechanismus erzeugt eine temporäre Tabelle; bei verschlüsselter DB funktioniert das identisch, solange die Connection bereits entschlüsselt ist. Kein Unterschied.
- **Konkurrierender Reindex während Migration:** Die Migration läuft beim App-Start (vor dem Worker-Start in der Lifespan). Solange deploy-Reihenfolge „migrate → start worker" ist, keine Race.
- **Mehrere Modelle parallel:** Das Composite-PK-Schema erlaubt das, aber der Plan exposed diesen Vorteil nicht als Feature. Kommt optional in einer späteren Phase (sanfter Reindex-Rollover).
- **embed_dimensions auf settings:** Bleibt unverändert — dient weiter als global-expected-dim-Warnflag. `dim` auf `entry_embeddings` ist per-row authoritativ.
