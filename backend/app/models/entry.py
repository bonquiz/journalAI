from datetime import date, datetime

from sqlalchemy import Date, DateTime, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_transcript: Mapped[str | None] = mapped_column(Text)
    chat_history: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    tags: Mapped[list["EntryTag"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )
    embeddings: Mapped[list["EntryEmbedding"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )
