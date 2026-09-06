"""add AI-selected multi-repository task scopes

Revision ID: 0049_task_repository_scopes
Revises: 0048_notification_retry_schedule
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0049_task_repository_scopes"
down_revision = "0048_notification_retry_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_repository_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("selected_by", sa.String(30), nullable=False, server_default="INTAKE"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "repository_id", name="uq_task_repository_scope"),
    )
    op.create_index("ix_task_repository_scopes_task", "task_repository_scopes", ["task_id"])
    op.create_index(
        "ix_task_repository_scopes_repository", "task_repository_scopes", ["repository_id"]
    )
    op.execute(
        """
        INSERT INTO task_repository_scopes
            (id, task_id, repository_id, selected_by, reason, confidence, is_primary, created_at)
        SELECT gen_random_uuid(), id, repository_id, 'LEGACY',
               'Migrated from the legacy primary repository', NULL, true, created_at
        FROM tasks
        WHERE repository_id IS NOT NULL
        ON CONFLICT (task_id, repository_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_task_repository_scopes_repository", table_name="task_repository_scopes")
    op.drop_index("ix_task_repository_scopes_task", table_name="task_repository_scopes")
    op.drop_table("task_repository_scopes")
