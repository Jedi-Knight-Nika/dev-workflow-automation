"""repository index completion timestamp

Revision ID: 0013_repository_indexed_at
Revises: 0012_worker_nodes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_repository_indexed_at"
down_revision: str | None = "0012_worker_nodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("indexed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("repositories", "indexed_at")
