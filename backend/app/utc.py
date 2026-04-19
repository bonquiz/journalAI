"""Naive UTC datetime helper.

We keep DB timestamps as naive UTC (SQLAlchemy stores datetimes without tz info
by default on SQLite). `datetime.utcnow()` is deprecated in Python 3.13; this
helper produces the same value via the timezone-aware API, then drops tz so the
values remain directly comparable with SQLAlchemy-loaded rows.
"""
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
