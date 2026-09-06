"""add repository archival lifecycle

Revision ID: 0047_repository_archival
Revises: 0046_integration_sync_state
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_repository_archival"
down_revision: str | None = "0046_integration_sync_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.create_index("ix_repositories_archived_at", "repositories", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_repositories_archived_at", table_name="repositories")
    op.drop_column("repositories", "archived_at")
