from app.application.ports.event_queries import EventQueries, EventView


class QueryEvents:
    def __init__(self, queries: EventQueries) -> None:
        self._queries = queries

    async def latest_id(self) -> int:
        return await self._queries.latest_id()

    async def after(self, event_id: int, limit: int = 100) -> list[EventView]:
        return await self._queries.after(event_id, max(1, min(limit, 500)))
