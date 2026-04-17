import io
import json
import zipfile

import pytest

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.models.tag import EntryTag, Tag
from app.services.import_ import ImportError as AppImportError, parse_export_zip


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(EntryTag).delete()
        db.query(Entry).delete()
        db.query(Tag).delete()
        db.query(AppSettings).delete()
        db.commit()


def _zip_with(payload: dict | str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        zf.writestr("entries.json", body)
    return buf.getvalue()


def _valid_payload() -> dict:
    return {
        "version": "1",
        "exported_at": "2026-04-17T10:00:00Z",
        "app": "journalAI",
        "entries": [{
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "entry_date": "2026-04-17",
            "title": "T",
            "content": "C",
            "tags": ["work"],
            "raw_transcript": None,
            "chat_history": None,
            "created_at": "2026-04-17T10:00:00Z",
            "updated_at": "2026-04-17T10:00:00Z",
        }],
        "tags": [{"name": "work"}],
    }


def test_parse_valid_zip():
    payload = parse_export_zip(_zip_with(_valid_payload()))
    assert payload["version"] == "1"
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["title"] == "T"


def test_parse_rejects_missing_entries_json():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other.json", "{}")
    with pytest.raises(AppImportError, match="entries.json"):
        parse_export_zip(buf.getvalue())


def test_parse_rejects_extra_files():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("entries.json", json.dumps(_valid_payload()))
        zf.writestr("extra.txt", "noise")
    with pytest.raises(AppImportError, match="genau"):
        parse_export_zip(buf.getvalue())


def test_parse_rejects_wrong_version():
    p = _valid_payload()
    p["version"] = "2"
    with pytest.raises(AppImportError, match="version"):
        parse_export_zip(_zip_with(p))


def test_parse_rejects_invalid_json():
    with pytest.raises(AppImportError, match="JSON"):
        parse_export_zip(_zip_with("not-json"))


def test_parse_rejects_corrupt_zip():
    with pytest.raises(AppImportError, match="ZIP"):
        parse_export_zip(b"not-a-zip-file")
