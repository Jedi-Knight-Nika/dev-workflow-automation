from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import Settings


def test_one_initial_revision_can_generate_sql_without_a_database() -> None:
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    revisions = ScriptDirectory.from_config(config)
    assert revisions.get_heads() == ["0001_initial"]
    assert len(list(revisions.walk_revisions())) == 1
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE developer_sessions" in sql
    assert "CREATE TABLE team_agent_profiles" in sql
    assert "INSERT INTO teams" in sql
    assert "ALTER TABLE" not in sql
    assert "CREATE EXTENSION" not in sql
    assert "DROP TABLE" not in sql


def test_fresh_installation_never_enables_paid_execution_or_legacy_workers() -> None:
    # Model defaults, not a developer's shell/.env overrides.
    defaults = Settings.model_fields
    assert defaults["new_fixed_lifecycle"].default is True
    for field in (
        "scheduler_enabled",
        "legacy_executor",
        "legacy_workflow_routing",
        "repository_rag_enabled",
        "developer_harness_codex",
        "developer_harness_claude",
    ):
        assert defaults[field].default is False


def test_snapshots_are_frozen_sql_not_live_metadata_creation() -> None:
    source = Path("migrations/versions/0001_initial.py").read_text()
    assert "app.db.models" not in source
    assert "create_all" not in source
    sql = Path("migrations/initial_schema.sql").read_text()
    assert "CREATE UNIQUE INDEX uq_task_assignments_active" in sql
    assert "WHERE status IN ('QUEUED', 'RUNNING')" in sql
    assert "ck_team_concurrency" in sql


@pytest.mark.parametrize(
    "overrides",
    [
        {"legacy_executor": True},
        {"legacy_workflow_routing": True},
        {"new_fixed_lifecycle": True, "repository_rag_enabled": True},
        {"scheduler_enabled": True, "new_fixed_lifecycle": False},
    ],
)
def test_retired_runtime_configuration_fails_before_dispatch_or_embedding(overrides) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **overrides)
