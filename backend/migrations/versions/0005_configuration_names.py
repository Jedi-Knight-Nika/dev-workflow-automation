"""Canonical integration configuration keys."""

revision = "0005_configuration_names"
down_revision = "0004_token_efficiency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    raise RuntimeError("Keep canonical integration configuration")
