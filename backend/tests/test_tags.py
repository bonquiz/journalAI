from fastapi.testclient import TestClient

from app.auth.password import hash_password
from app.auth.sessions import create_session
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models.settings import AppSettings
from app.models.tag import Tag


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.query(Tag).delete()
        db.add_all([Tag(name="alpha"), Tag(name="beta"), Tag(name="gamma")])
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(Tag).delete()
        db.query(AppSettings).delete()
        db.commit()


def test_tags_list_sorted():
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/tags", cookies={"session": sid})
    assert r.status_code == 200
    assert r.json() == ["alpha", "beta", "gamma"]


def test_tags_requires_auth():
    with TestClient(app) as c:
        r = c.get("/api/tags")
    assert r.status_code == 401
