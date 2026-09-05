"""add provider-neutral manual task properties

Revision ID: 0032_manual_task_properties
Revises: 0031_roles_and_agents
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_manual_task_properties"
down_revision: str | None = "0031_roles_and_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("project_name", sa.String(255)))
    op.add_column("tasks", sa.Column("labels", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("tasks", sa.Column("estimate", sa.Numeric(8, 2)))


def downgrade() -> None:
    op.drop_column("tasks", "estimate")
    op.drop_column("tasks", "labels")
    op.drop_column("tasks", "project_name")
