import uuid
from typing import Protocol

from app.domain.tasks import Task


class WorkspaceTaskNotFound(Exception):
    pass


class WorkspaceConflict(Exception):
    pass


class WorkspaceUnavailable(Exception):
    pass


class WorkspaceWorkflow(Protocol):
    async def prepare(self, task_id: uuid.UUID) -> Task: ...
