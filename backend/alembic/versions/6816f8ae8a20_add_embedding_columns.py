"""add embedding columns

Revision ID: 6816f8ae8a20
Revises: e3cb482e6e29
Create Date: 2026-04-17 15:31:14.690664

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6816f8ae8a20'
down_revision: Union[str, Sequence[str], None] = 'e3cb482e6e29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("entries", sa.Column("embedding", sa.LargeBinary(), nullable=True))
    op.add_column("entries", sa.Column("embedding_model", sa.String(), nullable=True))
    op.add_column("entries", sa.Column("embedding_updated_at", sa.DateTime(), nullable=True))
    op.add_column("settings", sa.Column("embed_dimensions", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("settings", "embed_dimensions")
    op.drop_column("entries", "embedding_updated_at")
    op.drop_column("entries", "embedding_model")
    op.drop_column("entries", "embedding")
