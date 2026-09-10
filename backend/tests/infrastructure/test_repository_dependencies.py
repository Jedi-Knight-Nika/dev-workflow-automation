import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import sqlite

from app.repositories.application.ports.repository_management import (
    CreateRepositoryCommand,
    ManagedRepositoryConflict,
)
from app.repositories.infrastructure.management import SqlAlchemyRepositoryManagementWorkflow


@pytest.mark.asyncio
@pytest.mark.parametrize("referenced", [False, True])
async def test_repository_delete_reuses_lock_and_preserves_source_dependency_guard(referenced):
    repository_id = uuid4()
    repository = SimpleNamespace(id=repository_id)
    integrations = (
        [
            SimpleNamespace(
                provider_name="trello", configuration={"repository_id": str(repository_id)}
            )
        ]
        if referenced
        else []
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=repository),
        scalars=AsyncMock(return_value=Mock(all=Mock(return_value=integrations))),
        delete=AsyncMock(),
        commit=AsyncMock(),
    )
    workflow = SqlAlchemyRepositoryManagementWorkflow(session)
    workflow._context = AsyncMock(return_value=({}, []))
    if referenced:
        with pytest.raises(ManagedRepositoryConflict):
            await workflow.delete(repository_id)
        session.delete.assert_not_awaited()
        session.commit.assert_not_awaited()
    else:
        await workflow.delete(repository_id)
        session.delete.assert_awaited_once_with(repository)
        session.commit.assert_awaited_once()
    session.get.assert_awaited_once()
    assert session.get.call_args.kwargs["with_for_update"] is True
    projection = str(session.scalars.call_args.args[0]).split("FROM", 1)[0]
    assert "configuration" in projection and "provider_name" in projection
    assert "credential" not in projection and "secret" not in projection


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_id,conflict", [("b", False), ("a", True)])
async def test_import_duplicate_query_matches_exact_provider_id_pairs(existing_id, conflict):
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE TABLE repositories (id TEXT, provider TEXT, external_repo_id TEXT)"
        )
        connection.execute(
            "INSERT INTO repositories VALUES (?, ?, ?)", ("id", "github", existing_id)
        )

        async def scalar(statement):
            sql = str(
                statement.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
            )
            return connection.execute(sql).fetchone()[0]

        session = SimpleNamespace(
            scalar=AsyncMock(side_effect=scalar), add_all=Mock(), commit=AsyncMock()
        )
        workflow = SqlAlchemyRepositoryManagementWorkflow(session)
        workflow._views = AsyncMock(return_value=[])
        commands = [
            CreateRepositoryCommand(provider, identifier, "owner", "repo", "url", "main")
            for provider, identifier in (("github", "a"), ("gitlab", "b"))
        ]
        if conflict:
            with pytest.raises(ManagedRepositoryConflict, match="already imported"):
                await workflow.import_batch(commands)
            session.add_all.assert_not_called()
            session.commit.assert_not_awaited()
        else:
            await workflow.import_batch(commands)
            session.add_all.assert_called_once()
            session.commit.assert_awaited_once()
    finally:
        connection.close()
