"""First-run bootstrap: seed the single AppSettings row from APP_PASSWORD env."""
from app.auth.password import hash_password
from app.config import settings as env
from app.db import Base, SessionLocal, engine
from app.models.settings import AppSettings


def ensure_bootstrap() -> None:
    """Idempotent: creates tables if missing, seeds settings row only if absent."""
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.get(AppSettings, 1) is not None:
            return
        db.add(
            AppSettings(
                id=1,
                password_hash=hash_password(env.app_password),
                coach_prompt=None,
                summary_prompt=None,
            )
        )
        db.commit()
