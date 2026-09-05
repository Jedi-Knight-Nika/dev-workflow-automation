import uuid

from app.application.ports.task_memory import TaskMemoryQueries


class QueryTaskMemory:
    def __init__(self, queries: TaskMemoryQueries) -> None:
        self._queries = queries

    async def memory(self, task_id: uuid.UUID) -> dict[str, object]:
        return await self._queries.memory(task_id)

    async def checkpoints(self, task_id: uuid.UUID) -> list[dict[str, object]]:
        return await self._queries.checkpoints(task_id)

    async def contexts(self, task_id: uuid.UUID) -> list[dict[str, object]]:
        return await self._queries.contexts(task_id)

    async def job_context(self, job_id: uuid.UUID) -> dict[str, object]:
        return await self._queries.job_context(job_id)
