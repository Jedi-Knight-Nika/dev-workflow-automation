"""persist terminal runtime ownership

Revision ID: 0040_terminal_runtime_ownership
Revises: 0039_task_archival
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_terminal_runtime_ownership"
down_revision: str | None = "0039_task_archival"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("terminal_sessions", sa.Column("runtime_owner_id", sa.String(255)))
    op.add_column(
        "terminal_sessions", sa.Column("runtime_heartbeat_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("terminal_sessions", "runtime_heartbeat_at")
    op.drop_column("terminal_sessions", "runtime_owner_id")
