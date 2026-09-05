"""durable job retry schedule

Revision ID: 0014_job_retry_schedule
Revises: 0013_repository_indexed_at
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_job_retry_schedule"
down_revision: str | None = "0013_repository_indexed_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("retry_not_before", sa.DateTime(timezone=True)))
    op.create_index("ix_jobs_retry_not_before", "jobs", ["retry_not_before"])


def downgrade() -> None:
    op.drop_index("ix_jobs_retry_not_before", table_name="jobs")
    op.drop_column("jobs", "retry_not_before")
