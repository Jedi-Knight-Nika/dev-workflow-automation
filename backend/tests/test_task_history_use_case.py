import uuid

import pytest

from app.application.tasks import QueryTaskHistory


class FakeTaskHistoryQueries:
    def __init__(self) -> None:
        self.calls: list[tuple[str, uuid.UUID]] = []

    async def jobs(self, task_id: uuid.UUID) -> list[object]:
        self.calls.append(("jobs", task_id))
        return []

    async def events(self, task_id: uuid.UUID) -> list[object]:
        self.calls.append(("events", task_id))
        return []

    async def validations(self, task_id: uuid.UUID) -> list[object]:
        self.calls.append(("validations", task_id))
        return []

    async def findings(self, task_id: uuid.UUID) -> list[object]:
        self.calls.append(("findings", task_id))
        return []


@pytest.mark.asyncio
async def test_task_history_delegates_every_read_to_query_port() -> None:
    task_id = uuid.uuid4()
    queries = FakeTaskHistoryQueries()
    history = QueryTaskHistory(queries)  # type: ignore[arg-type]

    assert await history.jobs(task_id) == []
    assert await history.events(task_id) == []
    assert await history.validations(task_id) == []
    assert await history.findings(task_id) == []
    assert queries.calls == [
        ("jobs", task_id),
        ("events", task_id),
        ("validations", task_id),
        ("findings", task_id),
    ]
