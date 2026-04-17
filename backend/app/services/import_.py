"""Import-Service: Parse, Plan, Apply für Export-ZIPs."""
import io
import json
import zipfile
from typing import Any

SUPPORTED_VERSIONS = {"1"}


class ImportError(Exception):
    """Geworfen bei Format-/Validierungs-Fehlern. Route-Layer mappt auf HTTP 400."""


def parse_export_zip(blob: bytes) -> dict[str, Any]:
    """Validiert und parst ein Export-ZIP. Wirft ImportError bei Fehlern."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob), "r")
    except zipfile.BadZipFile as exc:
        raise ImportError("ungültiges ZIP") from exc

    with zf:
        names = set(zf.namelist())
        if names != {"entries.json"}:
            if "entries.json" not in names:
                raise ImportError("entries.json fehlt im ZIP")
            raise ImportError("ZIP muss genau entries.json enthalten")
        try:
            raw = zf.read("entries.json").decode("utf-8")
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ImportError(f"entries.json ist kein gültiges JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ImportError("entries.json muss ein Objekt sein")

    version = payload.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise ImportError(f"unbekannte version: {version!r}")

    if not isinstance(payload.get("entries"), list):
        raise ImportError("entries muss ein Array sein")
    if not isinstance(payload.get("tags", []), list):
        raise ImportError("tags muss ein Array sein")

    return payload


from datetime import date as _date
from sqlalchemy.orm import Session

from app.models.entry import Entry as EntryModel
from app.models.tag import EntryTag, Tag as TagModel
from app.schemas.entries import new_id as new_entry_id
from app.utc import utc_now

VALID_MODES = {"skip", "copy", "overwrite"}


def _parse_date(v: Any) -> _date:
    if isinstance(v, _date):
        return v
    return _date.fromisoformat(str(v))


def _set_entry_tags(db: Session, entry_id: str, names: list[str]) -> None:
    db.query(EntryTag).filter(EntryTag.entry_id == entry_id).delete()
    for n in set(names):
        db.add(EntryTag(entry_id=entry_id, tag_name=n))


def run_import(
    db: Session,
    payload: dict[str, Any],
    *,
    mode: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Einheitlicher Import-Pfad: validiert + schreibt; bei dry_run rollback statt commit."""
    if mode not in VALID_MODES:
        raise ImportError(f"invalid mode: {mode!r}")

    entries = payload.get("entries", [])

    # Existierende Entry-IDs
    incoming_ids = {e["id"] for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)}
    existing_ids: set[str] = set()
    if incoming_ids:
        rows = db.query(EntryModel.id).filter(EntryModel.id.in_(incoming_ids)).all()
        existing_ids = {r[0] for r in rows}

    # Tag-Namen aus payload.tags[] und entries[*].tags[] sammeln (nur Strings)
    incoming_tag_names: set[str] = set()
    for t in payload.get("tags", []):
        if isinstance(t, dict) and isinstance(t.get("name"), str):
            incoming_tag_names.add(t["name"])
    for e in entries:
        if isinstance(e, dict):
            for n in e.get("tags", []) or []:
                if isinstance(n, str):
                    incoming_tag_names.add(n)

    existing_tag_names: set[str] = set()
    if incoming_tag_names:
        rows = db.query(TagModel.name).filter(TagModel.name.in_(incoming_tag_names)).all()
        existing_tag_names = {r[0] for r in rows}

    tags_merged = len(existing_tag_names & incoming_tag_names)
    tags_new = len(incoming_tag_names - existing_tag_names)

    for name in incoming_tag_names - existing_tag_names:
        db.add(TagModel(name=name))
    db.flush()

    new_count = 0
    conflict_count = 0
    errors: list[dict[str, Any]] = []

    try:
        for idx, raw in enumerate(entries):
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
                errors.append({"index": idx, "id": None, "reason": "missing or invalid id"})
                continue
            eid = raw["id"]

            try:
                entry_date = _parse_date(raw["entry_date"])
                title = raw["title"]
                if not isinstance(title, str):
                    raise ValueError("title must be str")
                if len(title) > 200:
                    raise ValueError("title too long (max 200)")
                content = raw["content"]
                if not isinstance(content, str):
                    raise ValueError("content must be str")
                tags_raw = raw.get("tags") or []
                if not isinstance(tags_raw, list) or any(not isinstance(t, str) for t in tags_raw):
                    raise ValueError("tags must be list[str]")
                tags = list(tags_raw)
                raw_transcript = raw.get("raw_transcript")
                if raw_transcript is not None and not isinstance(raw_transcript, str):
                    raise ValueError("raw_transcript must be str or null")
                chat_history = raw.get("chat_history")
                if chat_history is not None and not isinstance(chat_history, list):
                    raise ValueError("chat_history must be list or null")
                chat_history_json = json.dumps(chat_history) if chat_history else None
            except (KeyError, ValueError, TypeError) as exc:
                errors.append({"index": idx, "id": eid, "reason": str(exc)})
                continue

            is_conflict = eid in existing_ids
            if is_conflict:
                conflict_count += 1
                if mode == "skip":
                    continue
                if mode == "copy":
                    new_id_val = new_entry_id()
                    db.add(EntryModel(
                        id=new_id_val,
                        entry_date=entry_date,
                        title=title,
                        content=content,
                        raw_transcript=raw_transcript,
                        chat_history=chat_history_json,
                    ))
                    db.flush()
                    _set_entry_tags(db, new_id_val, tags)
                    continue
                # overwrite
                existing = db.get(EntryModel, eid)
                existing.entry_date = entry_date
                existing.title = title
                existing.content = content
                existing.raw_transcript = raw_transcript
                existing.chat_history = chat_history_json
                existing.updated_at = utc_now()
                existing.embedding = None
                existing.embedding_model = None
                existing.embedding_updated_at = None
                db.flush()
                _set_entry_tags(db, eid, tags)
                continue

            new_count += 1
            db.add(EntryModel(
                id=eid,
                entry_date=entry_date,
                title=title,
                content=content,
                raw_transcript=raw_transcript,
                chat_history=chat_history_json,
            ))
            db.flush()
            _set_entry_tags(db, eid, tags)
    except Exception:
        db.rollback()
        raise

    would_apply = new_count if mode == "skip" else new_count + conflict_count

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return {
        "dry_run": dry_run,
        "mode": mode,
        "total_in_file": len(entries),
        "new_entries": new_count,
        "conflicts": conflict_count,
        "would_apply": would_apply,
        "tags_new": tags_new,
        "tags_merged": tags_merged,
        "errors": errors,
    }
