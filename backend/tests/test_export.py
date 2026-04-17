import io
import json
import zipfile
from datetime import date

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.models.tag import EntryTag, Tag
from app.schemas.entries import new_id
from app.services.export import build_export_payload, export_zip_bytes


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


def _clear():
    with SessionLocal() as db:
        db.query(EntryTag).delete()
        db.query(Entry).delete()
        db.query(Tag).delete()
        db.commit()


def test_build_export_payload_empty():
    _clear()
    with SessionLocal() as db:
        payload = build_export_payload(db)
    assert payload["version"] == "1"
    assert payload["app"] == "journalAI"
    assert "exported_at" in payload
    assert payload["entries"] == []
    assert payload["tags"] == []


def test_build_export_payload_with_entry():
    _clear()
    with SessionLocal() as db:
        db.add(Tag(name="work"))
        db.add(Tag(name="reflection"))
        eid = new_id()
        e = Entry(
            id=eid,
            entry_date=__import__("datetime").date(2026, 4, 17),
            title="Hello",
            content="# heading\nbody",
            raw_transcript="raw",
            chat_history=json.dumps([{"role": "user", "content": "hi"}]),
        )
        db.add(e)
        db.add(EntryTag(entry_id=eid, tag_name="work"))
        db.add(EntryTag(entry_id=eid, tag_name="reflection"))
        db.commit()
        payload = build_export_payload(db)

    assert len(payload["entries"]) == 1
    entry = payload["entries"][0]
    assert entry["id"] == eid
    assert entry["entry_date"] == "2026-04-17"
    assert entry["title"] == "Hello"
    assert entry["content"] == "# heading\nbody"
    assert entry["raw_transcript"] == "raw"
    assert entry["chat_history"] == [{"role": "user", "content": "hi"}]
    assert sorted(entry["tags"]) == ["reflection", "work"]
    assert "created_at" in entry and "updated_at" in entry

    tag_names = sorted(t["name"] for t in payload["tags"])
    assert tag_names == ["reflection", "work"]


def test_export_zip_bytes_structure():
    _clear()
    with SessionLocal() as db:
        db.add(Tag(name="work"))
        db.add(Entry(
            id=new_id(),
            entry_date=date(2026, 4, 17),
            title="T", content="C",
        ))
        db.commit()
        blob = export_zip_bytes(db)

    assert isinstance(blob, bytes)
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        names = zf.namelist()
        assert names == ["entries.json"]
        data = json.loads(zf.read("entries.json").decode("utf-8"))
        assert data["version"] == "1"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["title"] == "T"


def test_export_timestamps_have_z_suffix():
    _clear()
    with SessionLocal() as db:
        db.add(Entry(id=new_id(), entry_date=date(2026, 4, 17), title="TZ", content="c"))
        db.commit()
        payload = build_export_payload(db)
    assert payload["exported_at"].endswith("Z")
    assert payload["entries"][0]["created_at"].endswith("Z")
    assert payload["entries"][0]["updated_at"].endswith("Z")
