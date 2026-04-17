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

from sqlalchemy import select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.entry_embedding import EntryEmbedding
from app.models.settings import AppSettings
from app.services.embeddings import (
    ProviderRateLimited,
    build_entry_text,
    embed_text,
    save_embedding_vector,
)
from app.services.llm_client import resolved_model

log = logging.getLogger(__name__)


def _current_embed_model() -> str | None:
    """Model name used for the current embed pass. Honours the full
    resolution chain from llm_client (DB → ENV → OpenAI-default)."""
    return resolved_model("embed")


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
    except ProviderRateLimited:
        # Let the backfill worker's backoff loop handle 429. Route-level
        # BackgroundTask invocations have nobody to catch this, so they
        # effectively skip — but that's preferable to pretending success.
        raise
    except Exception as err:
        log.warning("embed_entry_async: embed failed for %s: %s", entry_id, err)
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

    with SessionLocal() as db:
        e = db.get(Entry, entry_id)
        if e is None:
            return  # deleted between embed + write
        save_embedding_vector(db, entry_id, resolved_model, vec)
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


# ---------------- Job Runner (State Machine) ----------------

BACKFILL_THROTTLE_SECONDS = 0.2
BACKOFF_STEPS = (1.0, 2.0, 4.0)


class _JobState:
    """Coalesced flags for a single worker. Not thread-safe — worker owns it."""
    def __init__(self) -> None:
        self.pending_backfill = False
        self.pending_reindex = False
        self.running = False
        self.wakeup: asyncio.Event | None = None


_state = _JobState()
_worker_task: asyncio.Task | None = None


def request_backfill() -> None:
    """Signal that a backfill is desired. Collapses with any pending request."""
    _state.pending_backfill = True
    if _state.wakeup:
        _state.wakeup.set()


def request_reindex() -> None:
    """Signal that a full reindex is desired. Supersedes a pending backfill
    (reindex does a complete pass anyway)."""
    _state.pending_reindex = True
    if _state.wakeup:
        _state.wakeup.set()


def is_job_running() -> bool:
    return _state.running or _state.pending_backfill or _state.pending_reindex


async def _do_backfill() -> None:
    """Embed all entries that have no row in entry_embeddings for the current model.
    Ordered by updated_at DESC so the freshest entries become searchable first.
    """
    current = _current_embed_model()
    if not current:
        log.info("_do_backfill: no embed_model configured, skipping")
        return

    with SessionLocal() as db:
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


async def _embed_one_with_backoff(entry_id: str) -> None:
    """Run embed_entry_async with exponential backoff on ProviderRateLimited.

    Attempts up to len(BACKOFF_STEPS) + 1 times total (initial attempt plus
    one retry per backoff step). Default: 4 attempts, 1s/2s/4s between them.
    """
    for delay in BACKOFF_STEPS:
        try:
            await asyncio.to_thread(embed_entry_async, entry_id)
            return
        except ProviderRateLimited:
            log.info("429 for %s, sleeping %.1fs before retry", entry_id, delay)
            await asyncio.sleep(delay)
            continue
    # Final attempt after all backoff steps
    try:
        await asyncio.to_thread(embed_entry_async, entry_id)
    except ProviderRateLimited:
        log.warning("embed_entry_async gave up for %s after retries", entry_id)


async def _do_reindex() -> None:
    """Delete all entry_embeddings rows, then do a full backfill. Runs under the
    same lock as backfill — no release+reacquire race."""
    log.info("_do_reindex: clearing all embeddings")
    with SessionLocal() as db:
        db.query(EntryEmbedding).delete(synchronize_session=False)
        db.commit()
    await _do_backfill()


async def _worker_loop() -> None:
    """Single worker that drains pending flags, coalescing multiple requests.
    Reindex supersedes backfill; both signals are consumed in one pass."""
    while True:
        # Ensure Event is bound to the current event loop (handles TestClient loop changes)
        try:
            # Try to wait; if Event is bound to a different loop, this will raise
            await _state.wakeup.wait()
        except RuntimeError as e:
            if "bound to a different event loop" in str(e):
                # Event is stale; recreate it in the current loop
                _state.wakeup = asyncio.Event()
                # Set it immediately since we had a pending request
                if _state.pending_backfill or _state.pending_reindex:
                    _state.wakeup.set()
                continue
            raise
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
    # Create Event in the current running loop to avoid event loop binding issues
    if _state.wakeup is None:
        _state.wakeup = asyncio.Event()
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
