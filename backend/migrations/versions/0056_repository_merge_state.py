"""Track delivery completion independently for each task repository."""

import sqlalchemy as sa
from alembic import op

revision = "0056_repository_merge_state"
down_revision = "0055_combined_deliverer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_repository_scopes", sa.Column("merged_at", sa.DateTime(timezone=True)))
    op.add_column("task_repository_scopes", sa.Column("merge_commit_sha", sa.String(64)))


def downgrade() -> None:
    op.drop_column("task_repository_scopes", "merge_commit_sha")
    op.drop_column("task_repository_scopes", "merged_at")
