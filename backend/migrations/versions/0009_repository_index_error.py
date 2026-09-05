"""repository index diagnostics

Revision ID: 0009_repository_index_error
Revises: 0008_knowledge_chunks
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_repository_index_error"
down_revision: str | None = "0008_knowledge_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("index_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("repositories", "index_error")
