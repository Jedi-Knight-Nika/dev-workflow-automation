import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import IndexStatus, Repository
from app.infrastructure.persistence.repository_management import (
    SqlAlchemyRepositoryManagementWorkflow,
)

pytestmark = pytest.mark.asyncio


async def test_repository_summary_and_archive_use_real_postgres(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    repository_id = uuid.uuid4()
    try:
        async with postgres_session_factory() as session:
            session.add(
                Repository(
                    id=repository_id,
                    provider="github",
                    external_repo_id=f"resource-test-{repository_id}",
                    owner="integration-test",
                    name="resources",
                    clone_url="https://example.test/resources.git",
                    default_branch="main",
                    enabled=True,
                    index_status=IndexStatus.NOT_INDEXED,
                )
            )
            await session.commit()

        async with postgres_session_factory() as session:
            workflow = SqlAlchemyRepositoryManagementWorkflow(session)
            repositories = await workflow.list()
            repository = next(item for item in repositories if item.id == repository_id)
            assert repository.code_status == "NOT_PREPARED"
            assert repository.knowledge_status == "NOT_PREPARED"
            assert repository.active_tasks_count == 0

            archived = await workflow.set_archived(repository_id, True)
            assert archived.archived_at is not None
            assert archived.code_status == "DISABLED"
            assert all(item.id != repository_id for item in await workflow.list())
            assert any(item.id == repository_id for item in await workflow.list(True))
    finally:
        async with postgres_session_factory() as session:
            await session.execute(delete(Repository).where(Repository.id == repository_id))
            await session.commit()
