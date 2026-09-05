import uuid

from app.application.ports.task_queries import TaskQueries
from app.application.tasks.change_lifecycle import TaskNotFound
from app.domain.tasks import Task


class ListTasks:
    def __init__(self, queries: TaskQueries) -> None:
        self._queries = queries

    async def execute(self, limit: int) -> list[Task]:
        return await self._queries.list(limit)


class GetTask:
    def __init__(self, queries: TaskQueries) -> None:
        self._queries = queries

    async def execute(self, task_id: uuid.UUID) -> Task:
        task = await self._queries.get(task_id)
        if task is None:
            raise TaskNotFound("Task not found")
        return task
