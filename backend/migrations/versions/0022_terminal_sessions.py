"""durable controlled terminal sessions

Revision ID: 0022_terminal_sessions
Revises: 0021_tester_role
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_terminal_sessions"
down_revision: str | None = "0021_tester_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "terminal_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("node_id", sa.Uuid()),
        sa.Column("status", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("cols", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("rows", sa.Integer(), nullable=False, server_default="32"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("exit_code", sa.Integer()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "terminal_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("terminal_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_terminal_events_session_sequence", "terminal_events", ["session_id", "sequence"]
    )


def downgrade() -> None:
    op.drop_table("terminal_events")
    op.drop_table("terminal_sessions")
