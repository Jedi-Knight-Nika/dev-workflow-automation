"""task pull request state

Revision ID: 0006_pull_requests
Revises: 0005_workspaces
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_pull_requests"
down_revision: str | None = "0005_workspaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("pull_request_number", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("pull_request_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "pull_request_url")
    op.drop_column("tasks", "pull_request_number")
