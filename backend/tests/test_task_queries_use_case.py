import uuid
from datetime import UTC, datetime

import pytest

from app.application.tasks import GetTask, ListTasks, TaskNotFound
from app.domain.tasks import Task, TaskState


def task() -> Task:
    now = datetime.now(UTC)
    return Task(
        uuid.uuid4(),
        "Query task",
        "",
        3,
        TaskState.NEW,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        False,
        now,
        now,
    )


class FakeTaskQueries:
    def __init__(self, tasks: list[Task]) -> None:
        self.tasks = tasks
        self.limit: int | None = None

    async def list(self, limit: int) -> list[Task]:
        self.limit = limit
        return self.tasks[:limit]

    async def get(self, task_id: uuid.UUID) -> Task | None:
        return next((item for item in self.tasks if item.id == task_id), None)


@pytest.mark.asyncio
async def test_list_tasks_uses_query_port_limit() -> None:
    expected = task()
    queries = FakeTaskQueries([expected])
    assert await ListTasks(queries).execute(25) == [expected]
    assert queries.limit == 25


@pytest.mark.asyncio
async def test_get_task_returns_domain_snapshot_or_not_found() -> None:
    expected = task()
    queries = FakeTaskQueries([expected])
    assert await GetTask(queries).execute(expected.id) is expected
    with pytest.raises(TaskNotFound):
        await GetTask(queries).execute(uuid.uuid4())
