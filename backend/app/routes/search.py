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
