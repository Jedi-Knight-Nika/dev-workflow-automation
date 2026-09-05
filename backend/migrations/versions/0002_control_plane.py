"""add integrations repositories and agent configuration"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_control_plane"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    integration_status = sa.Enum(
        "DISCONNECTED", "CONFIGURED", "CONNECTED", "ERROR", name="integrationstatus"
    )
    index_status = sa.Enum(
        "NOT_INDEXED", "QUEUED", "INDEXING", "READY", "FAILED", name="indexstatus"
    )
    job_role = postgresql.ENUM(
        "INTAKE", "THINKER", "EXECUTOR", "REVIEWER", name="jobrole", create_type=False
    )
    op.create_table(
        "integrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider_type", sa.String(50), nullable=False),
        sa.Column("provider_name", sa.String(50), nullable=False, unique=True),
        sa.Column("status", integration_status, nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("external_repo_id", sa.String(255), nullable=False),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("clone_url", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("latest_sha", sa.String(64)),
        sa.Column("indexed_sha", sa.String(64)),
        sa.Column("index_status", index_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "external_repo_id", name="uq_repository_external"),
    )
    op.create_table(
        "agent_configs",
        sa.Column("role", job_role, primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_configs")
    op.drop_table("repositories")
    op.drop_table("integrations")
    sa.Enum(name="indexstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="integrationstatus").drop(op.get_bind(), checkfirst=True)
