from fastapi import APIRouter

from app.db import SessionLocal
from app.models.tag import Tag

router = APIRouter(prefix="/api")


@router.get("/tags")
async def list_tags() -> list[str]:
    with SessionLocal() as db:
        return sorted(t.name for t in db.query(Tag).all())
