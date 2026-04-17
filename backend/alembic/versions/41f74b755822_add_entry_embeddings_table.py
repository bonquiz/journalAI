"""add entry_embeddings table

Revision ID: 41f74b755822
Revises: 6816f8ae8a20
Create Date: 2026-04-17 19:04:31.170023

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '41f74b755822'
down_revision: Union[str, Sequence[str], None] = '6816f8ae8a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entry_embeddings",
        sa.Column("entry_id", sa.String(), sa.ForeignKey("entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("entry_id", "model"),
    )


def downgrade() -> None:
    op.drop_table("entry_embeddings")
