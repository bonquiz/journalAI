from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.models.tag import EntryTag, Tag

HEADERS = {"x-csrf-token": "t"}


def cookies(sid: str) -> dict[str, str]:
    return {"session": sid, "csrf": "t"}


def _seed_entries():
    """Create three entries with overlapping tags.

    e1: alpha, beta
    e2: beta
    e3: gamma
    """
    with SessionLocal() as db:
        db.query(EntryTag).delete()
        db.query(Entry).delete()
        db.query(Tag).delete()
        for n in ("alpha", "beta", "gamma"):
            db.add(Tag(name=n))
        db.add_all([
            Entry(id="e1", entry_date=date.today(), title="t1", content="c1"),
            Entry(id="e2", entry_date=date.today(), title="t2", content="c2"),
            Entry(id="e3", entry_date=date.today(), title="t3", content="c3"),
        ])
        db.flush()
        db.add_all([
            EntryTag(entry_id="e1", tag_name="alpha"),
            EntryTag(entry_id="e1", tag_name="beta"),
            EntryTag(entry_id="e2", tag_name="beta"),
            EntryTag(entry_id="e3", tag_name="gamma"),
        ])
        db.commit()


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()
    _seed_entries()


def teardown_module():
    with SessionLocal() as db:
        db.query(EntryTag).delete()
        db.query(Entry).delete()
        db.query(Tag).delete()
        db.query(AppSettings).delete()
        db.commit()


def test_tags_list_sorted():
    _seed_entries()
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/tags", cookies={"session": sid})
    assert r.status_code == 200
    assert r.json() == ["alpha", "beta", "gamma"]


def test_tags_requires_auth():
    with TestClient(app) as c:
        r = c.get("/api/tags")
    assert r.status_code == 401


def test_tag_stats_returns_counts():
    _seed_entries()
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/tags/stats", cookies={"session": sid})
    assert r.status_code == 200
    stats = {row["name"]: row["count"] for row in r.json()}
    assert stats == {"alpha": 1, "beta": 2, "gamma": 1}


def test_rename_moves_links():
    _seed_entries()
    sid = create_session()
    with TestClient(app) as c:
        r = c.put(
            "/api/tags/alpha",
            json={"new_name": "adventure"},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    assert r.json() == {"name": "adventure", "count": 1}
    with SessionLocal() as db:
        assert db.get(Tag, "alpha") is None
        links = [
            row[0]
            for row in db.execute(
                text("SELECT tag_name FROM entry_tags WHERE entry_id='e1'")
            ).all()
        ]
        assert "adventure" in links
        assert "alpha" not in links


def test_rename_to_existing_dedupes():
    _seed_entries()
    sid = create_session()
    # e1 is linked to both alpha AND beta. Rename alpha→beta must collapse.
    with TestClient(app) as c:
        r = c.put(
            "/api/tags/alpha",
            json={"new_name": "beta"},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    assert r.json()["name"] == "beta"
    # beta was linked to e1, e2 — after merge still 2 (alpha's e1 link collapses).
    assert r.json()["count"] == 2
    with SessionLocal() as db:
        assert db.get(Tag, "alpha") is None


def test_delete_cascades_links():
    _seed_entries()
    sid = create_session()
    with TestClient(app) as c:
        r = c.delete("/api/tags/beta", cookies=cookies(sid), headers=HEADERS)
    assert r.status_code == 204
    with SessionLocal() as db:
        assert db.get(Tag, "beta") is None
        count = db.query(EntryTag).filter_by(tag_name="beta").count()
        assert count == 0


def test_merge_multiple_sources_into_target():
    _seed_entries()
    sid = create_session()
    with TestClient(app) as c:
        r = c.post(
            "/api/tags/merge",
            json={"sources": ["alpha", "gamma"], "target": "beta"},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    # All three entries now reachable via beta (e1 via alpha, e2 already had beta, e3 via gamma)
    assert r.json() == {"name": "beta", "count": 3}
    with SessionLocal() as db:
        assert db.get(Tag, "alpha") is None
        assert db.get(Tag, "gamma") is None


def test_rename_missing_is_404():
    _seed_entries()
    sid = create_session()
    with TestClient(app) as c:
        r = c.put(
            "/api/tags/does-not-exist",
            json={"new_name": "x"},
            cookies=cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 404
