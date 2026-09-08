import uuid

from app.engineering.application.change_lifecycle import TaskNotFound
from app.engineering.application.ports.task_queries import TaskListFilters, TaskQueries, TaskView


class ListTasks:
    def __init__(self, queries: TaskQueries) -> None:
        self._queries = queries

    async def execute(self, limit: int, filters: TaskListFilters | None = None) -> list[TaskView]:
        return await self._queries.list(limit, filters or TaskListFilters())


class GetTask:
    def __init__(self, queries: TaskQueries) -> None:
        self._queries = queries

    async def execute(self, task_id: uuid.UUID) -> TaskView:
        task = await self._queries.get(task_id)
        if task is None:
            raise TaskNotFound("Task not found")
        return task
