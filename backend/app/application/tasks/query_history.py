import uuid

from app.application.ports.job_enqueueing import EnqueuedJob
from app.application.ports.task_history import (
    ReviewFindingView,
    TaskEventView,
    TaskHistoryQueries,
    ValidationView,
)


class QueryTaskHistory:
    def __init__(self, queries: TaskHistoryQueries) -> None:
        self._queries = queries

    async def jobs(self, task_id: uuid.UUID) -> list[EnqueuedJob]:
        return await self._queries.jobs(task_id)

    async def events(self, task_id: uuid.UUID) -> list[TaskEventView]:
        return await self._queries.events(task_id)

    async def validations(self, task_id: uuid.UUID) -> list[ValidationView]:
        return await self._queries.validations(task_id)

    async def findings(self, task_id: uuid.UUID) -> list[ReviewFindingView]:
        return await self._queries.findings(task_id)
