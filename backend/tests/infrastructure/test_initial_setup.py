from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.platform.configuration.settings import Settings


def test_initial_and_additive_revisions_can_generate_sql_without_a_database() -> None:
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    revisions = ScriptDirectory.from_config(config)
    assert revisions.get_heads() == ["0006_canonical_identifiers"]
    assert len(list(revisions.walk_revisions())) == 6
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE developer_sessions" in sql
    assert "CREATE TABLE team_agent_profiles" in sql
    assert "INSERT INTO teams" in sql
    assert "ALTER TABLE ai_runs" in sql
    assert "CREATE TABLE developer_context_generations" in sql
    assert "CREATE EXTENSION" not in sql
    assert "DROP TABLE" not in sql
    assert "CREATE TABLE runner_resource_bindings" in sql
    assert "CREATE TABLE task_forecasts" in sql


def test_fresh_installation_never_enables_paid_execution() -> None:
    defaults = Settings.model_fields
    for field in ("scheduler_enabled", "developer_harness_codex", "developer_harness_claude"):
        assert defaults[field].default is False


def test_snapshots_are_frozen_sql_not_live_metadata_creation() -> None:
    source = Path("migrations/versions/0001_initial.py").read_text()
    assert "app.platform.persistence.registry" not in source
    assert "create_all" not in source
    sql = Path("migrations/initial_schema.sql").read_text()
    assert "CREATE UNIQUE INDEX uq_task_assignments_active" in sql
    assert "WHERE status IN ('QUEUED', 'RUNNING')" in sql
    assert "ck_team_concurrency" in sql
