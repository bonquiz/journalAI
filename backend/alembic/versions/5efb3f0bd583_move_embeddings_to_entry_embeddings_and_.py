"""move embeddings to entry_embeddings and drop old columns

Revision ID: 5efb3f0bd583
Revises: 41f74b755822
Create Date: 2026-04-17 20:06:27.359184

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5efb3f0bd583'
down_revision: str | Sequence[str] | None = '41f74b755822'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Copy any existing vectors into entry_embeddings. dim is derived from
    # blob length / 4 (float32). Rows with NULL embedding or NULL model are skipped.
    op.execute(
        """
        INSERT INTO entry_embeddings (entry_id, model, dim, vector, created_at)
        SELECT
            id,
            embedding_model,
            CAST(LENGTH(embedding) / 4 AS INTEGER),
            embedding,
            COALESCE(embedding_updated_at, CURRENT_TIMESTAMP)
        FROM entries
        WHERE embedding IS NOT NULL AND embedding_model IS NOT NULL
        """
    )

    with op.batch_alter_table("entries") as batch:
        batch.drop_column("embedding_updated_at")
        batch.drop_column("embedding_model")
        batch.drop_column("embedding")


def downgrade() -> None:
    with op.batch_alter_table("entries") as batch:
        batch.add_column(sa.Column("embedding", sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column("embedding_model", sa.String(), nullable=True))
        batch.add_column(sa.Column("embedding_updated_at", sa.DateTime(), nullable=True))

    # Best-effort restore: pick the newest row per entry. If multiple models
    # coexist (new architecture feature), only the newest is preserved on downgrade.
    op.execute(
        """
        UPDATE entries
        SET
            embedding = (
                SELECT vector FROM entry_embeddings
                WHERE entry_embeddings.entry_id = entries.id
                ORDER BY created_at DESC LIMIT 1
            ),
            embedding_model = (
                SELECT model FROM entry_embeddings
                WHERE entry_embeddings.entry_id = entries.id
                ORDER BY created_at DESC LIMIT 1
            ),
            embedding_updated_at = (
                SELECT created_at FROM entry_embeddings
                WHERE entry_embeddings.entry_id = entries.id
                ORDER BY created_at DESC LIMIT 1
            )
        WHERE EXISTS (
            SELECT 1 FROM entry_embeddings WHERE entry_embeddings.entry_id = entries.id
        )
        """
    )
