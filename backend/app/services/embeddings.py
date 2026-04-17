"""Embedding vector operations for semantic search."""
from __future__ import annotations

import numpy as np
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
