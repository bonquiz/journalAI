import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.security.rate_limit import limiter
from app.services.embedding_jobs import is_job_running, request_reindex
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


@router.post("/reindex", status_code=202)
@limiter.limit("1/minute")
async def reindex(request: Request) -> dict:
    request_reindex()
    return {"ok": True}
