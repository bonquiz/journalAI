import re
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    domain: str = "localhost"
    app_password: str
    db_encryption_key: str
    session_secret: str
    secret_key_wrap: str
    db_path: str = "/app/data/journal.db"

    session_idle_minutes: int = 10
    session_absolute_hours: int = 12
    max_upload_mb: int = 25

    stt_base_url: str = "https://api.openai.com/v1"
    stt_api_key: str = ""
    stt_model: str = "whisper-1"

    chat_base_url: str = "https://api.openai.com/v1"
    chat_api_key: str = ""
    chat_model: str = "gpt-4o-mini"

    embed_base_url: str = "https://api.openai.com/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-small"

    tts_base_url: str = "https://api.openai.com/v1"
    tts_api_key: str = ""
    tts_model: str = "tts-1"

    @field_validator("db_encryption_key", "session_secret", "secret_key_wrap")
    @classmethod
    def _validate_hex_secret(cls, v: str) -> str:
        if len(v) < 64 or not re.fullmatch(r"[0-9a-fA-F]+", v):
            raise ValueError(
                "must be at least 64 hex characters. Generate with: openssl rand -hex 32"
            )
        return v


# Module-level instance; wrapped so pytest collection doesn't fail when env
# vars are not yet set (conftest autouse fixtures run per-test, after collection).
try:
    settings = Settings()
except Exception:
    settings = None  # type: ignore[assignment]  # lazy: callers must use Settings() directly or check for None
