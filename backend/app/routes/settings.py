from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.auth.password import hash_password, verify_password
from app.auth.sessions import invalidate_all
from app.crypto import unwrap_secret, wrap_secret
from app.db import SessionLocal
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.schemas.settings import PasswordChange, SettingsOut, SettingsPatch

router = APIRouter(prefix="/api/settings")


def _mask(wrapped: str | None) -> str | None:
    if not wrapped:
        return None
    raw = unwrap_secret(wrapped)
    return "…" + raw[-4:] if len(raw) >= 4 else "…"


def _settings_to_out(s: AppSettings) -> SettingsOut:
    return SettingsOut(
        stt_base_url=s.stt_base_url,
        stt_api_key_masked=_mask(s.stt_api_key_wrapped),
        stt_model=s.stt_model,
        chat_base_url=s.chat_base_url,
        chat_api_key_masked=_mask(s.chat_api_key_wrapped),
        chat_model=s.chat_model,
        embed_base_url=s.embed_base_url,
        embed_api_key_masked=_mask(s.embed_api_key_wrapped),
        embed_model=s.embed_model,
        tts_base_url=s.tts_base_url,
        tts_api_key_masked=_mask(s.tts_api_key_wrapped),
        tts_model=s.tts_model,
        tts_voice=s.tts_voice,
        tts_speed=s.tts_speed,
        system_prompt=s.system_prompt,
        totp_enabled=bool(s.totp_secret),
    )


@router.get("")
async def get_settings() -> SettingsOut:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None:
            raise HTTPException(500, "settings not initialized")
        return _settings_to_out(s)


@router.put("")
async def update_settings(body: SettingsPatch) -> dict:
    data = body.model_dump(exclude_unset=True)
    mismatch = None
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None:
            raise HTTPException(500, "settings not initialized")
        old_embed_model = s.embed_model

        for cap in ("stt", "chat", "embed", "tts"):
            if f"{cap}_base_url" in data:
                setattr(s, f"{cap}_base_url", data[f"{cap}_base_url"])
            if f"{cap}_api_key" in data:
                setattr(s, f"{cap}_api_key_wrapped", wrap_secret(data[f"{cap}_api_key"]))
            if f"{cap}_model" in data:
                setattr(s, f"{cap}_model", data[f"{cap}_model"])
        if "tts_voice" in data:
            # Empty string or whitespace resets override to NULL (spec §5.4).
            raw_voice = data["tts_voice"]
            if isinstance(raw_voice, str) and raw_voice.strip():
                s.tts_voice = raw_voice.strip()
            else:
                s.tts_voice = None
        if "tts_speed" in data:
            # None or empty string resets override to NULL.
            raw_speed = data["tts_speed"]
            s.tts_speed = None if raw_speed in (None, "") else float(raw_speed)
        if "system_prompt" in data:
            s.system_prompt = data["system_prompt"]

        new_embed_model = s.embed_model
        if (
            "embed_model" in data
            and old_embed_model
            and new_embed_model
            and old_embed_model != new_embed_model
        ):
            affected = int(db.scalar(
                select(func.count()).select_from(Entry).where(
                    Entry.embedding_model.is_not(None),
                    Entry.embedding_model != new_embed_model,
                )
            ) or 0)
            if affected > 0:
                mismatch = {
                    "old_model": old_embed_model,
                    "new_model": new_embed_model,
                    "affected_entries": affected,
                }
        db.commit()
        db.refresh(s)
        payload = _settings_to_out(s).model_dump()

    if mismatch:
        payload["warning"] = "embedding_model_mismatch"
        payload["embedding_mismatch"] = mismatch
    return payload


@router.post("/password")
async def change_password(body: PasswordChange) -> dict:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None or not verify_password(body.old_password, s.password_hash):
            raise HTTPException(401, "wrong password")
        s.password_hash = hash_password(body.new_password)
        db.commit()
    # Spec §5.2: invalidate all sessions after password change
    invalidate_all()
    return {"ok": True}
