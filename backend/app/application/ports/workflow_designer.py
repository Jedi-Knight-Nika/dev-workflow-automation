from typing import Protocol

from app.domain.workflows import WorkflowGraphData


class WorkflowVersionConflict(RuntimeError):
    pass


class WorkflowDesigner(Protocol):
    async def get(self) -> WorkflowGraphData: ...
    async def replace(self, graph: WorkflowGraphData) -> WorkflowGraphData: ...
