from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.models.tag import EntryTag, Tag


HEADERS = {"x-csrf-token": "t"}
def cookies(sid): return {"session": sid, "csrf": "t"}


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


def _create(c, sid, **overrides):
    body = {"title": "T", "content": "C", "tags": ["a"], "entry_date": "2026-04-14"}
    body.update(overrides)
    return c.post("/api/entries", json=body, cookies=cookies(sid), headers=HEADERS)


def test_create_list_get_update_delete():
    sid = create_session()
    with TestClient(app) as c:
        r = _create(c, sid)
        assert r.status_code == 201
        eid = r.json()["id"]

        items = c.get("/api/entries", cookies=cookies(sid)).json()["items"]
        assert any(i["id"] == eid for i in items)

        detail = c.get(f"/api/entries/{eid}", cookies=cookies(sid)).json()
        assert detail["tags"] == ["a"]

        r2 = c.put(f"/api/entries/{eid}", json={"title": "T2"},
                   cookies=cookies(sid), headers=HEADERS)
        assert r2.status_code == 200
        assert r2.json()["title"] == "T2"

        r3 = c.delete(f"/api/entries/{eid}", cookies=cookies(sid), headers=HEADERS)
        assert r3.status_code == 204


def test_filter_by_tag():
    sid = create_session()
    with TestClient(app) as c:
        _create(c, sid, tags=["xfilter"])
        _create(c, sid, tags=["yfilter"])
        items = c.get("/api/entries?tags=xfilter", cookies=cookies(sid)).json()["items"]
    assert all("xfilter" in i["tags"] for i in items)
    assert len([i for i in items if "yfilter" in i["tags"]]) == 0


def test_substring_search():
    sid = create_session()
    with TestClient(app) as c:
        _create(c, sid, title="Einzigartiger Titel", content="body1")
        _create(c, sid, title="Anderer", content="body2")
        items = c.get("/api/entries?q=Einzigartiger", cookies=cookies(sid)).json()["items"]
    assert any(i["title"] == "Einzigartiger Titel" for i in items)
    assert all("Einzigartiger" in i["title"] or "Einzigartiger" in i["content"] for i in items)


def test_404_for_missing_entry():
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/entries/does-not-exist", cookies=cookies(sid))
    assert r.status_code == 404


def test_raw_transcript_and_chat_history_persisted():
    sid = create_session()
    with TestClient(app) as c:
        r = _create(c, sid,
                    raw_transcript="original voice text",
                    chat_history=[{"role": "user", "content": "hi"}])
        eid = r.json()["id"]
        detail = c.get(f"/api/entries/{eid}", cookies=cookies(sid)).json()
    assert detail["raw_transcript"] == "original voice text"
    assert detail["chat_history"] == [{"role": "user", "content": "hi"}]
