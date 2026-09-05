"""add configurable system agent roles

Revision ID: 0024_system_agent_configs
Revises: 0023_workflow_node_access
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_system_agent_configs"
down_revision: str | None = "0023_workflow_node_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE jobrole ADD VALUE IF NOT EXISTS 'ORCHESTRATOR'")
        op.execute("ALTER TYPE jobrole ADD VALUE IF NOT EXISTS 'DELIVERER'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    pass
