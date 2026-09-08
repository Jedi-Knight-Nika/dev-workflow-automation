"""Normalize stored application identifiers without changing business facts."""

from alembic import op

revision = "0006_canonical_identifiers"
down_revision = "0005_configuration_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.execute("""
        UPDATE ai_runs SET prompt_version = CASE
          WHEN lower(prompt_version) LIKE '%compact%' THEN 'developer.compaction'
          WHEN role_kind = 'INTERPRETER' THEN 'interpreter.classification'
          ELSE 'fixed'
        END
        WHERE prompt_version ~* '^v[0-9]'
    """)
    op.execute("""
        UPDATE team_agent_profiles SET prompt_version = 'fixed'
        WHERE prompt_version ~* '^v[0-9]'
    """)
    op.execute("""
        UPDATE task_events
        SET event_type = regexp_replace(event_type, '^V[0-9]+_', 'ENGINEERING_'),
            source = regexp_replace(source, '(engineering|scheduler)-v[0-9]+', '\\1', 'gi')
        WHERE event_type ~ '^V[0-9]+_' OR source ~* '(engineering|scheduler)-v[0-9]+'
    """)
    op.execute("""
        UPDATE settings_audit_events SET section = 'automation'
        WHERE section ~* '^v[0-9]+_automation$'
    """)
    op.execute("""
        UPDATE tasks SET branch_name = regexp_replace(branch_name, '^agent/v[0-9]+-', 'agent/task-')
        WHERE branch_name ~ '^agent/v[0-9]+-'
    """)


def downgrade() -> None:
    raise RuntimeError("Canonical identifiers are permanent")
