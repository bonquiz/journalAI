from app.auth.password import verify_password
from app.bootstrap import ensure_bootstrap
from app.db import Base, SessionLocal, engine
from app.models.settings import AppSettings


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    # Clean slate
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(AppSettings).delete()
        db.commit()


def test_bootstrap_creates_settings_row():
    ensure_bootstrap()
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        assert s is not None
        assert verify_password("testpw", s.password_hash)


def test_bootstrap_is_idempotent():
    ensure_bootstrap()
    ensure_bootstrap()
    ensure_bootstrap()
    with SessionLocal() as db:
        assert db.query(AppSettings).count() == 1
