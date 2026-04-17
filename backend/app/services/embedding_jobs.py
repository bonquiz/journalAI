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

import logging

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.services.embeddings import (
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
