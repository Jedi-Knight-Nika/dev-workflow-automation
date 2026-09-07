"""Repair nullable resilience state left by older deployments."""

import sqlalchemy as sa
from alembic import op

revision = "0057_health_defaults"
down_revision = "0056_repository_merge_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ORM defaults only apply to newly constructed objects; they do not repair
    # rows written by older versions.  Normalize those rows before enforcing
    # the invariant in the database.
    op.execute(
        sa.text("UPDATE health_states SET circuit_state = 'CLOSED' WHERE circuit_state IS NULL")
    )
    op.execute(
        sa.text(
            "UPDATE health_states SET consecutive_failures = 0 WHERE consecutive_failures IS NULL"
        )
    )
    op.alter_column("health_states", "circuit_state", nullable=False)
    op.alter_column("health_states", "consecutive_failures", nullable=False)


def downgrade() -> None:
    # Keep repaired values on downgrade; only remove the stricter constraint.
    op.alter_column("health_states", "consecutive_failures", nullable=True)
    op.alter_column("health_states", "circuit_state", nullable=True)
