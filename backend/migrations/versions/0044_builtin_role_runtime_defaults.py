"""seed purpose-fit runtime defaults for built-in roles

Revision ID: 0044_role_runtime_defaults
Revises: 0043_role_runtime_profiles
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0044_role_runtime_defaults"
down_revision: str | None = "0043_role_runtime_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET runtime_profile = (runtime_profile::jsonb || jsonb_build_object(
            'reasoning_default', CASE category
                WHEN 'PLANNING' THEN 'HIGH'
                WHEN 'EXECUTION' THEN 'HIGH'
                WHEN 'VALIDATION' THEN 'MEDIUM'
                WHEN 'REVIEW' THEN 'HIGH'
                WHEN 'DELIVERY' THEN 'LOW'
                ELSE 'MEDIUM'
            END,
            'reasoning_min', CASE
                WHEN category IN ('PLANNING', 'REVIEW') THEN 'MEDIUM'
                ELSE 'PROVIDER_DEFAULT'
            END,
            'reasoning_max', CASE
                WHEN category = 'PLANNING' THEN 'MAX'
                WHEN category = 'DELIVERY' THEN 'MEDIUM'
                ELSE 'HIGH'
            END
        ))::json
        WHERE built_in = true
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET runtime_profile = (runtime_profile::jsonb || jsonb_build_object(
            'reasoning_default', 'PROVIDER_DEFAULT',
            'reasoning_min', 'PROVIDER_DEFAULT',
            'reasoning_max', 'MAX'
        ))::json
        WHERE built_in = true
        """
    )
