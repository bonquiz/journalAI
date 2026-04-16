"""Database-backed session store with idle and absolute timeouts.

Session lifecycle:
- create_session() returns a 48-byte URL-safe random token, persisted with
  created_at = last_activity_at = now, expires_at = now + absolute hours.
- get_active_session(sid) returns the row, auto-deleting if idle or absolute
  timeout has passed.
- touch_session(sid) updates last_activity_at, but is throttled to at most one
  DB write per 30s to avoid contention under high request rates (SSE, etc.).
- invalidate_session(sid) hard-deletes one session; invalidate_all() wipes all
  (used after password change / TOTP activation per spec §5.2).
"""
import secrets
from datetime import datetime, timedelta

from app.config import settings
from app.db import SessionLocal
from app.models.session import AppSession

_TOUCH_INTERVAL = timedelta(seconds=30)


def create_session() -> str:
    sid = secrets.token_urlsafe(48)
    now = datetime.utcnow()
    with SessionLocal() as db:
        db.add(
            AppSession(
                id=sid,
                created_at=now,
                last_activity_at=now,
                expires_at=now + timedelta(hours=settings.session_absolute_hours),
            )
        )
        db.commit()
    return sid


def get_active_session(sid: str) -> AppSession | None:
    if not sid:
        return None
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        if s is None:
            return None
        now = datetime.utcnow()
        idle_limit = timedelta(minutes=settings.session_idle_minutes)
        if now - s.last_activity_at > idle_limit or now > s.expires_at:
            db.delete(s)
            db.commit()
            return None
        return s


def touch_session(sid: str) -> None:
    """Update last_activity_at, throttled to max 1 write per 30s."""
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        if s is None:
            return
        now = datetime.utcnow()
        if now - s.last_activity_at > _TOUCH_INTERVAL:
            s.last_activity_at = now
            db.commit()


def invalidate_session(sid: str) -> None:
    with SessionLocal() as db:
        s = db.get(AppSession, sid)
        if s is not None:
            db.delete(s)
            db.commit()


def invalidate_all() -> None:
    with SessionLocal() as db:
        db.query(AppSession).delete()
        db.commit()
