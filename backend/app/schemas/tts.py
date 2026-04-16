from pydantic import BaseModel, Field


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    voice: str | None = None
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
