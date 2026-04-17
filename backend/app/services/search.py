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
