from pydantic import BaseModel


class SettingsOut(BaseModel):
    stt_base_url: str | None = None
    stt_api_key_masked: str | None = None
    stt_model: str | None = None
    chat_base_url: str | None = None
    chat_api_key_masked: str | None = None
    chat_model: str | None = None
    embed_base_url: str | None = None
    embed_api_key_masked: str | None = None
    embed_model: str | None = None
    tts_base_url: str | None = None
    tts_api_key_masked: str | None = None
    tts_model: str | None = None
    system_prompt: str | None = None
    totp_enabled: bool = False


class SettingsPatch(BaseModel):
    stt_base_url: str | None = None
    stt_api_key: str | None = None
    stt_model: str | None = None
    chat_base_url: str | None = None
    chat_api_key: str | None = None
    chat_model: str | None = None
    embed_base_url: str | None = None
    embed_api_key: str | None = None
    embed_model: str | None = None
    tts_base_url: str | None = None
    tts_api_key: str | None = None
    tts_model: str | None = None
    system_prompt: str | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str
