"""Native context generations, bounded checkpoints and versioned token policy."""

import sqlalchemy as sa
from alembic import op

revision = "0004_token_efficiency"
down_revision = "0003_operational_configuration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.create_table(
        "developer_token_policies",
        sa.Column(
            "team_id", sa.Uuid(), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "developer_context_generations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "developer_session_id",
            sa.Uuid(),
            sa.ForeignKey("developer_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("native_thread_id", sa.String(255)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("harness", sa.String(24), nullable=False),
        sa.Column("requirement_version", sa.Integer(), nullable=False),
        sa.Column("policy", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("end_reason", sa.String(80)),
        sa.UniqueConstraint("developer_session_id", "sequence", name="uq_context_sequence"),
    )
    op.create_table(
        "developer_checkpoints",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "developer_session_id",
            sa.Uuid(),
            sa.ForeignKey("developer_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "context_generation_id",
            sa.Uuid(),
            sa.ForeignKey("developer_context_generations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requirement_version", sa.Integer(), nullable=False),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("checkpoint_digest", sa.String(64), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("ai_runs", sa.Column("context_generation_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_ai_context_generation",
        "ai_runs",
        "developer_context_generations",
        ["context_generation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("ai_runs", sa.Column("active_context_estimate", sa.Integer()))
    op.add_column("ai_runs", sa.Column("active_context_estimate_source", sa.String(80)))
    op.add_column("ai_runs", sa.Column("token_efficiency", sa.JSON()))


def downgrade() -> None:
    raise RuntimeError("Disable token enforcement; retain native generation and billing history")
