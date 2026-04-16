from datetime import datetime, timedelta

from app.auth.sessions import (
    create_session,
    get_active_session,
    invalidate_all,
    invalidate_session,
    touch_session,
)
from app.db import Base, SessionLocal, engine
from app.models.session import AppSession


def setup_module():
    Base.metadata.create_all(engine)


def _fast_forward(sid: str, delta: timedelta) -> None:
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        s.last_activity_at = datetime.utcnow() - delta
        db.commit()


def test_create_and_get():
    sid = create_session()
    assert get_active_session(sid) is not None


def test_idle_expiry():
    sid = create_session()
    _fast_forward(sid, timedelta(hours=1))  # well past 10-min idle default
    assert get_active_session(sid) is None


def test_absolute_expiry():
    sid = create_session()
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        s.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert get_active_session(sid) is None


def test_invalidate_single():
    sid = create_session()
    invalidate_session(sid)
    assert get_active_session(sid) is None


def test_invalidate_all():
    s1 = create_session()
    s2 = create_session()
    invalidate_all()
    assert get_active_session(s1) is None
    assert get_active_session(s2) is None


def test_touch_throttled_no_write_within_30s():
    sid = create_session()
    with SessionLocal() as db:
        before = db.get(AppSession, sid).last_activity_at
    touch_session(sid)  # within 30s window → should NOT update
    with SessionLocal() as db:
        after = db.get(AppSession, sid).last_activity_at
    assert after == before


def test_touch_updates_after_30s():
    sid = create_session()
    _fast_forward(sid, timedelta(seconds=45))
    touch_session(sid)
    with SessionLocal() as db:
        last = db.get(AppSession, sid).last_activity_at
    # Should be very close to now (definitely within last minute)
    assert datetime.utcnow() - last < timedelta(minutes=1)


def test_get_nonexistent():
    assert get_active_session("") is None
    assert get_active_session("does-not-exist") is None
