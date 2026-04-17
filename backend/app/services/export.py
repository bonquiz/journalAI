"""Export-Service: baut ein Dict im Export-Format (v1)."""
import json
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.entry import Entry
from app.models.tag import Tag
from app.utc import utc_now

EXPORT_VERSION = "1"


def build_export_payload(db: Session) -> dict[str, Any]:
    """Baut das Export-Dict. Reiner Builder, ohne I/O."""
    entries_out: list[dict[str, Any]] = []
    for e in db.query(Entry).options(selectinload(Entry.tags)).order_by(Entry.entry_date.desc(), Entry.created_at.desc()).all():
        entries_out.append({
            "id": e.id,
            "entry_date": e.entry_date.isoformat(),
            "title": e.title,
            "content": e.content,
            "tags": sorted({link.tag_name for link in e.tags}),
            "raw_transcript": e.raw_transcript,
            "chat_history": json.loads(e.chat_history) if e.chat_history else None,
            "created_at": e.created_at.isoformat() + ("Z" if e.created_at.tzinfo is None else ""),
            "updated_at": e.updated_at.isoformat() + ("Z" if e.updated_at.tzinfo is None else ""),
        })

    tags_out = [{"name": t.name} for t in db.query(Tag).order_by(Tag.name).all()]

    return {
        "version": EXPORT_VERSION,
        "exported_at": utc_now().isoformat() + "Z",
        "app": "journalAI",
        "entries": entries_out,
        "tags": tags_out,
    }
