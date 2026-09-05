import uuid

from app.application.ports.workspace_workflow import WorkspaceWorkflow
from app.domain.tasks import Task


class PrepareTaskWorkspace:
    def __init__(self, workflow: WorkspaceWorkflow) -> None:
        self._workflow = workflow

    async def execute(self, task_id: uuid.UUID) -> Task:
        return await self._workflow.prepare(task_id)
