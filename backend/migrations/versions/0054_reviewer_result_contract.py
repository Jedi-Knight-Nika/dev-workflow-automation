"""align reviewer result allowlist with runtime contract

Revision ID: 0054_reviewer_result_contract
Revises: 0053_task_message_edits
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0054_reviewer_result_contract"
down_revision: str | None = "0053_task_message_edits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET allowed_results = '["PASS","FAIL_ACTIONABLE","FAIL_ARCHITECTURAL","UNCERTAIN","NEEDS_HUMAN","BLOCKED"]'::json
        WHERE name = 'Reviewer'
          AND built_in = true
          AND allowed_results::text LIKE '%REVIEW_PASS%'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET allowed_results = '["REVIEW_PASS","FAIL_ACTIONABLE","FAIL_ARCHITECTURAL","NEEDS_HUMAN","BLOCKED"]'::json
        WHERE name = 'Reviewer'
          AND built_in = true
          AND allowed_results::text LIKE '%"PASS"%'
        """
    )
