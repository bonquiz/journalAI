from pydantic import BaseModel


class CoachPresetOut(BaseModel):
    key: str
    label: str
    text: str


class SettingsOut(BaseModel):
    stt_base_url: str | None = None
    stt_api_key_masked: str | None = None
    stt_model: str | None = None
    stt_resolved_base_url: str | None = None
    stt_resolved_model: str | None = None

    chat_base_url: str | None = None
    chat_api_key_masked: str | None = None
    chat_model: str | None = None
    chat_resolved_base_url: str | None = None
    chat_resolved_model: str | None = None

    embed_base_url: str | None = None
    embed_api_key_masked: str | None = None
    embed_model: str | None = None
    embed_resolved_base_url: str | None = None
    embed_resolved_model: str | None = None

    tts_base_url: str | None = None
    tts_api_key_masked: str | None = None
    tts_model: str | None = None
    tts_resolved_base_url: str | None = None
    tts_resolved_model: str | None = None

    tts_voice: str | None = None
    tts_speed: float | None = None

    coach_prompt: str | None = None
    summary_prompt: str | None = None
    coach_presets: list[CoachPresetOut] = []
    default_coach_preset_key: str = "therapist"

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
    tts_voice: str | None = None
    tts_speed: float | None = None
    coach_prompt: str | None = None
    summary_prompt: str | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str
