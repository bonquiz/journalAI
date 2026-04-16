"""Verify the SQLCipher engine writes encrypted pages that cannot be read
without the key."""
import os
import sqlite3

import pytest
from sqlalchemy import text

from app.db import engine


def test_engine_is_encrypted():
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE foo (id INTEGER)"))
        conn.execute(text("INSERT INTO foo VALUES (1)"))
        conn.commit()

    # Opening the same DB file with raw sqlite3 (no key) must fail
    db_path = os.environ["DB_PATH"]
    raw = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.DatabaseError):
        raw.execute("SELECT * FROM foo").fetchone()
    raw.close()
