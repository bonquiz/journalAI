from datetime import date, datetime, timedelta

from app.db import Base, SessionLocal, engine
from app.models.entry import Entry
from app.models.session import AppSession
from app.models.settings import AppSettings
from app.models.tag import EntryTag, Tag


def setup_module():
    Base.metadata.create_all(engine)


def test_entry_tag_many_to_many():
    with SessionLocal() as s:
        t = Tag(name="test-m2m")
        e = Entry(id="e1", entry_date=date.today(), title="t", content="c")
        s.add_all([t, e, EntryTag(entry_id="e1", tag_name="test-m2m")])
        s.commit()
        fetched = s.get(Entry, "e1")
        assert {link.tag_name for link in fetched.tags} == {"test-m2m"}


def test_session_expiry_fields():
    with SessionLocal() as s:
        sess = AppSession(
            id="sid-test",
            created_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        s.add(sess)
        s.commit()
        assert s.get(AppSession, "sid-test") is not None


def test_settings_singleton_constraint():
    # Clean slate — another test module may have left an id=1 row.
    with SessionLocal() as s:
        s.query(AppSettings).delete()
        s.commit()
    with SessionLocal() as s:
        s.add(AppSettings(id=1, password_hash="argon2-placeholder"))
        s.commit()
        # Inserting another row with id=2 must fail due to CHECK (id = 1).
        import pytest
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            s.add(AppSettings(id=2, password_hash="x"))
            s.commit()
        s.rollback()
    # Clean up so we don't contaminate subsequent tests.
    with SessionLocal() as s:
        s.query(AppSettings).delete()
        s.commit()


def test_entry_cascade_delete_tags():
    with SessionLocal() as s:
        s.add(Tag(name="cascade-test"))
        s.add(Entry(id="e-cascade", entry_date=date.today(), title="t", content="c"))
        s.flush()
        s.add(EntryTag(entry_id="e-cascade", tag_name="cascade-test"))
        s.commit()
        s.delete(s.get(Entry, "e-cascade"))
        s.commit()
        # Link row should be gone
        assert s.query(EntryTag).filter_by(entry_id="e-cascade").count() == 0


def test_entry_embedding_roundtrip():
    from datetime import date

    from app.db import Base, SessionLocal, engine
    from app.models.entry import Entry
    from app.models.entry_embedding import EntryEmbedding

    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.query(EntryEmbedding).delete()
        db.query(Entry).delete()
        db.add(Entry(id="ee1", entry_date=date(2026, 4, 1), title="t", content="c"))
        db.add(EntryEmbedding(entry_id="ee1", model="m1", dim=3, vector=b"\x00" * 12))
        db.commit()

        row = db.get(EntryEmbedding, ("ee1", "m1"))
        assert row is not None
        assert row.dim == 3
        assert len(row.vector) == 12

        # Cascade delete
        db.delete(db.get(Entry, "ee1"))
        db.commit()
        assert db.get(EntryEmbedding, ("ee1", "m1")) is None
