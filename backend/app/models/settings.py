from sqlalchemy import CheckConstraint, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AppSettings(Base):
    __tablename__ = "settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stt_base_url: Mapped[str | None] = mapped_column(String)
    stt_api_key_wrapped: Mapped[str | None] = mapped_column(String)
    stt_model: Mapped[str | None] = mapped_column(String)
    chat_base_url: Mapped[str | None] = mapped_column(String)
    chat_api_key_wrapped: Mapped[str | None] = mapped_column(String)
    chat_model: Mapped[str | None] = mapped_column(String)
    embed_base_url: Mapped[str | None] = mapped_column(String)
    embed_api_key_wrapped: Mapped[str | None] = mapped_column(String)
    embed_model: Mapped[str | None] = mapped_column(String)
    tts_base_url: Mapped[str | None] = mapped_column(String)
    tts_api_key_wrapped: Mapped[str | None] = mapped_column(String)
    tts_model: Mapped[str | None] = mapped_column(String)
    coach_prompt: Mapped[str | None] = mapped_column(Text)
    summary_prompt: Mapped[str | None] = mapped_column(Text)
    totp_secret: Mapped[str | None] = mapped_column(String)
    totp_pending_secret: Mapped[str | None] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    tts_voice: Mapped[str | None] = mapped_column(String)
    tts_speed: Mapped[float | None] = mapped_column(Float)
    embed_dimensions: Mapped[int | None] = mapped_column(Integer)
