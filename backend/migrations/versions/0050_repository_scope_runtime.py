"""add per-repository execution and delivery state

Revision ID: 0050_repository_scope_runtime
Revises: 0049_task_repository_scopes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0050_repository_scope_runtime"
down_revision: str | None = "0049_task_repository_scopes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task_repository_scopes", sa.Column("workspace_path", sa.Text()))
    op.add_column("task_repository_scopes", sa.Column("branch_name", sa.String(255)))
    op.add_column("task_repository_scopes", sa.Column("base_revision", sa.String(64)))
    op.add_column("task_repository_scopes", sa.Column("current_revision", sa.String(64)))
    op.add_column(
        "task_repository_scopes",
        sa.Column("changed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("task_repository_scopes", sa.Column("pull_request_number", sa.Integer()))
    op.add_column("task_repository_scopes", sa.Column("pull_request_url", sa.Text()))
    op.execute(
        """
        UPDATE task_repository_scopes AS scope
        SET workspace_path = task.workspace_path,
            branch_name = task.branch_name,
            current_revision = task.current_revision,
            pull_request_number = task.pull_request_number,
            pull_request_url = task.pull_request_url
        FROM tasks AS task
        WHERE scope.task_id = task.id AND scope.is_primary = true
        """
    )


def downgrade() -> None:
    for column in (
        "pull_request_url",
        "pull_request_number",
        "changed",
        "current_revision",
        "base_revision",
        "branch_name",
        "workspace_path",
    ):
        op.drop_column("task_repository_scopes", column)
