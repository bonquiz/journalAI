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
                score=float(item.get("score") or 0),
                reason=item.get("reason"),
            ))
        if not out:
            return _cosine_fallback(candidates, top_k)
        return out[:top_k]
    except Exception as exc:
        log.warning("rerank_results failed, using cosine order: %s", exc)
        return _cosine_fallback(candidates, top_k)


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
