"""Add operator preferences, current container observations and repository runtimes."""

import sqlalchemy as sa
from alembic import op

revision = "0003_operational_configuration"
down_revision = "0002_observability_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.create_table(
        "monitoring_configuration",
        sa.Column("id", sa.String(24), primary_key=True),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "container_observations",
        sa.Column("container_id", sa.String(64), primary_key=True),
        sa.Column("host_id", sa.String(80), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
    )
    op.create_table(
        "repository_runtime_profiles",
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("developer_image_ref", sa.String(500), nullable=False),
        sa.Column("validator_image_ref", sa.String(500), nullable=False),
        sa.Column("validation_commands", sa.JSON(), nullable=False),
        sa.Column("image_digest", sa.String(100)),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Disable supporting features and roll back the application; retain operator configuration and history"
    )
