import uuid

import pytest

from app.application.ports.event_queries import EventView
from app.application.query_events import QueryEvents


class FakeEventQueries:
    def __init__(self) -> None:
        self.limits: list[int] = []

    async def latest_id(self) -> int:
        return 42

    async def after(self, event_id: int, limit: int) -> list[EventView]:
        self.limits.append(limit)
        return [EventView(event_id + 1, uuid.UUID(int=1), "TASK_UPDATED")]


@pytest.mark.asyncio
async def test_event_queries_delegate_and_bound_replay_limit() -> None:
    adapter = FakeEventQueries()
    queries = QueryEvents(adapter)

    assert await queries.latest_id() == 42
    events = await queries.after(4, 10_000)

    assert events[0].id == 5
    assert adapter.limits == [500]
