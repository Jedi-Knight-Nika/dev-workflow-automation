"""add encrypted credentials and provider usage runs"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_provider_runtime"
down_revision = "0002_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("integrations", sa.Column("encrypted_credentials", sa.LargeBinary()))
    job_role = postgresql.ENUM(
        "INTAKE", "THINKER", "EXECUTOR", "REVIEWER", name="jobrole", create_type=False
    )
    op.create_table(
        "worker_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", job_role, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("provider_request_id", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_runs")
    op.drop_column("integrations", "encrypted_credentials")
