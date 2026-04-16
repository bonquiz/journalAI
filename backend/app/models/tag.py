from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Tag(Base):
    __tablename__ = "tags"
    name: Mapped[str] = mapped_column(String, primary_key=True)


class EntryTag(Base):
    __tablename__ = "entry_tags"

    entry_id: Mapped[str] = mapped_column(
        ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    tag_name: Mapped[str] = mapped_column(
        ForeignKey("tags.name", ondelete="CASCADE"), primary_key=True
    )

    entry: Mapped["Entry"] = relationship(back_populates="tags")  # type: ignore[name-defined]
