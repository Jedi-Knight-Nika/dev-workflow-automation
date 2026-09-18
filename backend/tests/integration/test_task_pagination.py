from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.engineering.application.ports.task_queries import TaskListFilters
from app.engineering.application.task_pagination import next_cursor
from app.engineering.infrastructure.queries import SqlAlchemyTaskQueries
from app.engineering.infrastructure.task_models import Task


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", ["priority", "created", "updated", "due"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_keyset_pages_cover_ties_and_null_due_dates_without_duplicates(
    postgres_session_factory, sort, direction
):
    prefix = f"paging-{uuid4()}"
    created_at = datetime.now(UTC)
    records = [
        Task(
            id=uuid4(),
            title=f"{prefix}-{index}",
            priority=index % 3,
            created_at=created_at,
            updated_at=created_at,
            due_at=None if index % 2 else created_at + timedelta(days=index % 3),
        )
        for index in range(11)
    ]
    async with postgres_session_factory.begin() as session:
        session.add_all(records)
    try:
        filters = TaskListFilters(search=prefix, sort=sort, direction=direction)
        async with postgres_session_factory() as session:
            queries = SqlAlchemyTaskQueries(session)
            expected = [view.task.id for view in await queries.list(100, filters)]
            seen = []
            for _ in range(10):
                page = await queries.list(3, filters)
                if not page:
                    break
                seen.extend(view.task.id for view in page)
                filters = replace(filters, cursor=next_cursor(page[-1], filters))
            assert seen == expected
            assert len(set(seen)) == len(records)
            with pytest.raises(ValueError, match="Invalid task cursor"):
                await queries.list(3, replace(filters, search="changed"))
    finally:
        async with postgres_session_factory.begin() as session:
            await session.execute(delete(Task).where(Task.title.startswith(prefix)))
