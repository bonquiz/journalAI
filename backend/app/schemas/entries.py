import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class EntryCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: str
    tags: list[str] = Field(default_factory=list)
    entry_date: date
    raw_transcript: str | None = None
    chat_history: list[dict] | None = None


class EntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    entry_date: date | None = None


class EntryOut(BaseModel):
    id: str
    entry_date: date
    title: str
    content: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class EntryDetail(EntryOut):
    raw_transcript: str | None = None
    chat_history: list[dict] | None = None


def new_id() -> str:
    return str(uuid.uuid4())
