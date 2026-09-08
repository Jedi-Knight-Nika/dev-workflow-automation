"""Exercise the real initial revision in disposable, rolled-back schemas."""

import importlib.util
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.platform.persistence.registry  # noqa: F401 - register the complete application metadata
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.engineering.infrastructure.task_models import Task
from app.platform.persistence.base import Base

DEFAULT_TEAM = UUID("00000000-0000-0000-0000-000000000001")


def initial_revision():
    path = Path("migrations/versions/0001_initial.py")
    spec = importlib.util.spec_from_file_location("initial_revision", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def supporting_revision(name="0002_observability_analytics"):
    path = Path(f"migrations/versions/{name}.py")
    spec = importlib.util.spec_from_file_location("supporting_revision", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def isolated_schema(connection: Connection) -> None:
    schema = "initial_setup_test_" + uuid4().hex
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))


def exercise_fresh_setup(connection: Connection) -> None:
    isolated_schema(connection)
    revision = initial_revision()
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        revision.upgrade()
        baseline_profiles = connection.execute(
            text("SELECT * FROM team_agent_profiles ORDER BY id")
        ).all()
        supporting_revision().upgrade()
        supporting_revision("0003_operational_configuration").upgrade()
        assert (
            connection.execute(text("SELECT * FROM team_agent_profiles ORDER BY id")).all()
            == baseline_profiles
        )
        assert set(inspect(connection).get_table_names()) == set(Base.metadata.tables)
        # Protect against losing FK/query indexes or model constraints when the
        # historical chain is discarded. This is actual PostgreSQL reflection.
        assert compare_metadata(context, Base.metadata) == []
        assert connection.execute(text("SELECT id, name FROM teams")).one() == (
            DEFAULT_TEAM,
            "Default team",
        )
        profiles = connection.execute(
            text(
                "SELECT role_kind, enabled, hard_budget_usd FROM team_agent_profiles ORDER BY role_kind"
            )
        ).all()
        assert profiles == [
            ("DEVELOPER", True, None),
            ("INTERPRETER", True, None),
            ("REVIEWER", False, None),
            ("THINKER", False, None),
        ]
        configuration = connection.scalar(
            text("SELECT configuration FROM team_automation_policies")
        )
        assert configuration["enrollment_enabled"] is False
        assert configuration["auto_merge"] is False
        assert configuration["repository_ids"] == []
        settings = connection.execute(
            text("SELECT timezone, default_task_view, settings_version FROM account_settings")
        ).one()
        assert settings == ("UTC", "board", 1)
        assert connection.scalar(text("SELECT count(*) FROM integrations")) == 7
        assert (
            connection.scalar(
                text("SELECT count(*) FROM integrations WHERE encrypted_credentials IS NOT NULL")
            )
            == 0
        )
        for table in (
            "tasks",
            "jobs",
            "ai_runs",
            "pricing_catalog",
        ):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        with pytest.raises(RuntimeError, match="empty database/schema"):
            revision.upgrade()
        with pytest.raises(RuntimeError, match="no destructive downgrade"):
            revision.downgrade()
        assert connection.scalar(text("SELECT count(*) FROM team_agent_profiles")) == 4


def exercise_existing_database(connection: Connection) -> None:
    isolated_schema(connection)
    connection.execute(text("CREATE TABLE old_ticket (title TEXT)"))
    connection.execute(text("INSERT INTO old_ticket VALUES ('Do not destroy this')"))
    with (
        Operations.context(MigrationContext.configure(connection)),
        pytest.raises(RuntimeError, match="Existing data was not changed"),
    ):
        initial_revision().upgrade()
    assert inspect(connection).get_table_names() == ["old_ticket"]
    assert connection.scalar(text("SELECT title FROM old_ticket")) == "Do not destroy this"


def exercise_supporting_upgrade_preserves_records(connection: Connection) -> None:
    isolated_schema(connection)
    with Operations.context(MigrationContext.configure(connection)):
        initial_revision().upgrade()
        task_id, session_id = uuid4(), uuid4()
        connection.execute(
            Task.__table__.insert().values(
                id=task_id, title="Existing ticket", team_id=DEFAULT_TEAM
            )
        )
        connection.execute(
            DeveloperSession.__table__.insert().values(
                id=session_id,
                task_id=task_id,
                harness="codex",
                harness_version="test",
                provider="test",
                model="test",
                native_session_id="preserved-native-session",
                workspace_path="/fixture/workspace",
                state_path="/fixture/state",
            )
        )
        connection.execute(
            AIRun.__table__.insert().values(
                task_id=task_id,
                session_id=session_id,
                role_kind="DEVELOPER",
                provider="test",
                model="test",
                prompt_version="test",
                provider_cost_usd="1.25",
                input_tokens=123,
                output_tokens=45,
            )
        )
        tables = inspect(connection).get_table_names()

        def snapshot():
            return {
                name: connection.execute(text(f'SELECT * FROM "{name}" ORDER BY 1')).all()
                for name in tables
            }

        before = snapshot()
        supporting_revision().upgrade()
        assert snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exercise",
    [
        exercise_fresh_setup,
        exercise_existing_database,
        exercise_supporting_upgrade_preserves_records,
    ],
)
async def test_initial_schema_is_complete_and_refuses_existing_data(
    postgres_session_factory: async_sessionmaker[AsyncSession], exercise
) -> None:
    async with postgres_session_factory() as session:
        try:
            connection = await session.connection()
            await connection.run_sync(exercise)
        finally:
            # PostgreSQL rolls back schema creation too; no application data is touched.
            await session.rollback()
