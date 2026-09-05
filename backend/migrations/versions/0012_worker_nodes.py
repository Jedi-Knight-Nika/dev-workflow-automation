"""persistent worker registry

Revision ID: 0012_worker_nodes
Revises: 0011_manual_takeover
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_worker_nodes"
down_revision: str | None = "0011_manual_takeover"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_nodes",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("worker_nodes")
