from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    system_prompt_override: str | None = None


class FinalizeRequest(BaseModel):
    messages: list[ChatMessage]
