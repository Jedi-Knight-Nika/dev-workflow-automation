"""add workflow node integration and repository access

Revision ID: 0023_workflow_node_access
Revises: 0022_terminal_sessions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_workflow_node_access"
down_revision: str | None = "0022_terminal_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_nodes",
        sa.Column("integration_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "workflow_nodes",
        sa.Column("repository_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("workflow_nodes", "repository_ids")
    op.drop_column("workflow_nodes", "integration_ids")
