"""bind tasks to repositories and add workspace leases"""

import sqlalchemy as sa
from alembic import op

revision = "0005_workspaces"
down_revision = "0004_github_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("local_path", sa.Text()))
    op.add_column(
        "tasks",
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("tasks", sa.Column("branch_name", sa.String(255)))
    op.add_column("tasks", sa.Column("workspace_path", sa.Text()))
    op.create_table(
        "workspace_leases",
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("workspace_leases")
    op.drop_column("tasks", "workspace_path")
    op.drop_column("tasks", "branch_name")
    op.drop_column("tasks", "repository_id")
    op.drop_column("repositories", "local_path")
