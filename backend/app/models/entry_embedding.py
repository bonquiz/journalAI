from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class EntryEmbedding(Base):
    __tablename__ = "entry_embeddings"

    entry_id: Mapped[str] = mapped_column(
        String, ForeignKey("entries.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String, primary_key=True)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), nullable=False
    )

    entry = relationship("Entry", back_populates="embeddings")
