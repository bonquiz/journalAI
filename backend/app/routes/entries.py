import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.entry import Entry
from app.models.tag import EntryTag, Tag
from app.schemas.entries import EntryCreate, EntryDetail, EntryOut, EntryUpdate, new_id

router = APIRouter(prefix="/api/entries")


def _ensure_tags(db, names: list[str]) -> None:
    for n in names:
        if db.get(Tag, n) is None:
            db.add(Tag(name=n))


def _tag_names(e: Entry) -> list[str]:
    return sorted({link.tag_name for link in e.tags})


def _to_detail(e: Entry) -> dict:
    return EntryDetail(
        id=e.id,
        entry_date=e.entry_date,
        title=e.title,
        content=e.content,
        tags=_tag_names(e),
        created_at=e.created_at,
        updated_at=e.updated_at,
        raw_transcript=e.raw_transcript,
        chat_history=json.loads(e.chat_history) if e.chat_history else None,
    ).model_dump(mode="json")


@router.post("", status_code=201)
async def create_entry(body: EntryCreate) -> dict:
    with SessionLocal() as db:
        e = Entry(
            id=new_id(),
            entry_date=body.entry_date,
            title=body.title,
            content=body.content,
            raw_transcript=body.raw_transcript,
            chat_history=json.dumps(body.chat_history) if body.chat_history else None,
        )
        db.add(e)
        _ensure_tags(db, body.tags)
        for n in set(body.tags):
            db.add(EntryTag(entry_id=e.id, tag_name=n))
        db.commit()
        db.refresh(e)
        return _to_detail(e)


@router.get("")
async def list_entries(
    tags: str = Query(default=""),
    q: str = Query(default=""),
    offset: int = 0,
    limit: int = 50,
) -> dict:
    tag_list = [t for t in tags.split(",") if t]
    with SessionLocal() as db:
        stmt = select(Entry).order_by(Entry.entry_date.desc(), Entry.created_at.desc())
        if tag_list:
            stmt = stmt.where(
                Entry.id.in_(
                    select(EntryTag.entry_id)
                    .where(EntryTag.tag_name.in_(tag_list))
                    .group_by(EntryTag.entry_id)
                    .having(func.count() == len(set(tag_list)))
                )
            )
        if q:
            like = f"%{q}%"
            stmt = stmt.where((Entry.title.ilike(like)) | (Entry.content.ilike(like)))
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(stmt.offset(offset).limit(limit)).all()
        return {
            "total": total or 0,
            "items": [
                EntryOut(
                    id=e.id,
                    entry_date=e.entry_date,
                    title=e.title,
                    content=e.content,
                    tags=_tag_names(e),
                    created_at=e.created_at,
                    updated_at=e.updated_at,
                ).model_dump(mode="json")
                for e in rows
            ],
        }


@router.get("/{eid}")
async def get_entry(eid: str) -> dict:
    with SessionLocal() as db:
        e = db.get(Entry, eid)
        if not e:
            raise HTTPException(404)
        return _to_detail(e)


@router.put("/{eid}")
async def update_entry(eid: str, body: EntryUpdate) -> dict:
    with SessionLocal() as db:
        e = db.get(Entry, eid)
        if not e:
            raise HTTPException(404)
        if body.title is not None:
            e.title = body.title
        if body.content is not None:
            e.content = body.content
        if body.entry_date is not None:
            e.entry_date = body.entry_date
        if body.tags is not None:
            db.query(EntryTag).filter(EntryTag.entry_id == eid).delete()
            _ensure_tags(db, body.tags)
            for n in set(body.tags):
                db.add(EntryTag(entry_id=eid, tag_name=n))
        e.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(e)
        return _to_detail(e)


@router.delete("/{eid}", status_code=204)
async def delete_entry(eid: str) -> None:
    with SessionLocal() as db:
        e = db.get(Entry, eid)
        if not e:
            raise HTTPException(404)
        db.delete(e)
        db.commit()
