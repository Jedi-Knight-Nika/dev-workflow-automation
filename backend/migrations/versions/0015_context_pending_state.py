"""add context-pending task state

Revision ID: 0015_context_pending_state
Revises: 0014_job_retry_schedule
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015_context_pending_state"
down_revision: str | None = "0014_job_retry_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE taskstate ADD VALUE IF NOT EXISTS 'CONTEXT_PENDING' AFTER 'NEW'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without rebuilding dependent columns.
    pass
