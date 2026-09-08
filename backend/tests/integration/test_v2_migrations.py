"""Execute the new additive revisions in a rolled-back, isolated schema.

The minimal legacy prerequisites deliberately avoid pgvector. This exercises
0058/0059 DDL and retention rules, not a full production-database upgrade.
"""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def revision(name: str):
    spec = importlib.util.spec_from_file_location(name, Path("migrations/versions") / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exercise(connection: Connection) -> None:
    foundation, automation = revision("0058_v2_foundation"), revision("0059_v2_automation")
    schema = "v2_migration_test_" + uuid4().hex
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
    for table in ("tasks", "teams", "jobs"):
        connection.execute(text(f"CREATE TABLE {table} (id UUID PRIMARY KEY, title TEXT)"))
    connection.execute(
        text("INSERT INTO tasks VALUES (:id, 'Preserve this legacy ticket')"), {"id": uuid4()}
    )
    with Operations.context(MigrationContext.configure(connection)):
        foundation.upgrade()
        automation.upgrade()
        assert connection.execute(
            text("SELECT title, execution_version, status FROM tasks")
        ).one() == ("Preserve this legacy ticket", 1, None)
        assert connection.scalar(text("SELECT count(*) FROM local_model_runs")) == 0
        team_id = uuid4()
        connection.execute(text("INSERT INTO teams(id) VALUES (:id)"), {"id": team_id})
        connection.execute(
            text("INSERT INTO team_automation_policies(team_id, configuration) VALUES (:id, '{}')"),
            {"id": team_id},
        )
        with pytest.raises(RuntimeError, match="Preserve"):
            automation.downgrade()
        connection.execute(
            text("DELETE FROM team_automation_policies WHERE team_id=:id"), {"id": team_id}
        )
        automation.downgrade()
        foundation.downgrade()
        assert connection.scalar(text("SELECT title FROM tasks")) == "Preserve this legacy ticket"


@pytest.mark.asyncio
async def test_additive_revisions_preserve_legacy_and_refuse_destructive_downgrade(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with postgres_session_factory() as session:
        try:
            connection = await session.connection()
            await connection.run_sync(exercise)
        finally:
            # PostgreSQL rolls back schema creation too; no app tables are touched.
            await session.rollback()
