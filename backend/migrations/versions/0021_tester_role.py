"""add tester agent role

Revision ID: 0021_tester_role
Revises: 0020_workflow_graph
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_tester_role"
down_revision: str | None = "0020_workflow_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE jobrole ADD VALUE IF NOT EXISTS 'TESTER'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    pass
