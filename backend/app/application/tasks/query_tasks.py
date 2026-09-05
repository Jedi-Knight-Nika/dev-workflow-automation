import uuid

from app.application.ports.task_queries import TaskListFilters, TaskQueries, TaskView
from app.application.tasks.change_lifecycle import TaskNotFound


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
