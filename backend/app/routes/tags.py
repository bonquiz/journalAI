"""Tag management routes.

- GET /api/tags            — flat list of tag names (used for autocomplete + filter).
- GET /api/tags/stats      — list of {name, count} rows for the management UI.
- PUT /api/tags/{name}     — rename a tag (moves all entry_tags links to the new name).
- DELETE /api/tags/{name}  — delete a tag and its links (entries survive, link rows go).
- POST /api/tags/merge     — merge one or more source tags into a target (dedupe + drop).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.tag import EntryTag, Tag

router = APIRouter(prefix="/api")


class TagRename(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=100)


class TagMerge(BaseModel):
    sources: list[str] = Field(..., min_length=1)
    target: str = Field(..., min_length=1, max_length=100)


class TagStat(BaseModel):
    name: str
    count: int


def _normalize(raw: str) -> str:
    return raw.strip().lower()


@router.get("/tags")
async def list_tags() -> list[str]:
    with SessionLocal() as db:
        return sorted(t.name for t in db.query(Tag).all())


@router.get("/tags/stats")
async def tag_stats() -> list[TagStat]:
    with SessionLocal() as db:
        stmt = (
            select(Tag.name, func.count(EntryTag.entry_id))
            .select_from(Tag)
            .outerjoin(EntryTag, EntryTag.tag_name == Tag.name)
            .group_by(Tag.name)
            .order_by(func.count(EntryTag.entry_id).desc(), Tag.name.asc())
        )
        return [TagStat(name=n, count=c or 0) for n, c in db.execute(stmt).all()]


@router.put("/tags/{name}")
async def rename_tag(name: str, body: TagRename) -> TagStat:
    old = _normalize(name)
    new = _normalize(body.new_name)
    if not new:
        raise HTTPException(400, "new_name must not be empty")
    if new == old:
        # nothing to do — return current stats
        with SessionLocal() as db:
            count = db.scalar(
                select(func.count()).select_from(EntryTag).where(EntryTag.tag_name == old)
            ) or 0
            return TagStat(name=old, count=count)

    with SessionLocal() as db:
        src = db.get(Tag, old)
        if src is None:
            raise HTTPException(404, "tag not found")
        target = db.get(Tag, new)
        if target is None:
            db.add(Tag(name=new))
            db.flush()
        # Move all links (dedupe if target already linked to the same entry)
        src_ids = [row[0] for row in db.execute(
            select(EntryTag.entry_id).where(EntryTag.tag_name == old)
        ).all()]
        existing_target_ids = set(row[0] for row in db.execute(
            select(EntryTag.entry_id).where(EntryTag.tag_name == new)
        ).all())
        for eid in src_ids:
            if eid in existing_target_ids:
                # link already exists under the new name → just drop the old link
                db.query(EntryTag).filter_by(entry_id=eid, tag_name=old).delete()
            else:
                db.query(EntryTag).filter_by(entry_id=eid, tag_name=old).update(
                    {"tag_name": new}
                )
        # Remove the old tag row now that no links reference it
        db.query(Tag).filter_by(name=old).delete()
        db.commit()
        count = db.scalar(
            select(func.count()).select_from(EntryTag).where(EntryTag.tag_name == new)
        ) or 0
        return TagStat(name=new, count=count)


@router.delete("/tags/{name}", status_code=204)
async def delete_tag(name: str) -> None:
    n = _normalize(name)
    with SessionLocal() as db:
        tag = db.get(Tag, n)
        if tag is None:
            raise HTTPException(404, "tag not found")
        # FK cascade removes entry_tags rows
        db.delete(tag)
        db.commit()


@router.post("/tags/merge")
async def merge_tags(body: TagMerge) -> TagStat:
    target = _normalize(body.target)
    sources = [s for s in (_normalize(x) for x in body.sources) if s and s != target]
    if not sources:
        raise HTTPException(400, "no distinct source tags given")

    with SessionLocal() as db:
        # Ensure target exists
        if db.get(Tag, target) is None:
            db.add(Tag(name=target))
            db.flush()

        # Collect entries already linked to target — for dedupe
        existing_target_ids = set(row[0] for row in db.execute(
            select(EntryTag.entry_id).where(EntryTag.tag_name == target)
        ).all())

        for src in sources:
            if db.get(Tag, src) is None:
                continue
            src_ids = [row[0] for row in db.execute(
                select(EntryTag.entry_id).where(EntryTag.tag_name == src)
            ).all()]
            for eid in src_ids:
                if eid in existing_target_ids:
                    db.query(EntryTag).filter_by(entry_id=eid, tag_name=src).delete()
                else:
                    db.query(EntryTag).filter_by(entry_id=eid, tag_name=src).update(
                        {"tag_name": target}
                    )
                    existing_target_ids.add(eid)
            db.query(Tag).filter_by(name=src).delete()

        db.commit()
        count = db.scalar(
            select(func.count()).select_from(EntryTag).where(EntryTag.tag_name == target)
        ) or 0
        return TagStat(name=target, count=count)
