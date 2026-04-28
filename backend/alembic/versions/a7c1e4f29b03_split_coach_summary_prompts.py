"""split coach and summary prompts

Revision ID: a7c1e4f29b03
Revises: 5efb3f0bd583
Create Date: 2026-04-28 12:00:00.000000

Renames AppSettings.system_prompt → coach_prompt (verlustfrei) und ergänzt
summary_prompt (NULLable). Downgrade dropt summary_prompt — dortiger Inhalt
geht verloren.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c1e4f29b03"
down_revision: str | Sequence[str] | None = "5efb3f0bd583"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.alter_column("system_prompt", new_column_name="coach_prompt")
        batch.add_column(sa.Column("summary_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.drop_column("summary_prompt")
        batch.alter_column("coach_prompt", new_column_name="system_prompt")
