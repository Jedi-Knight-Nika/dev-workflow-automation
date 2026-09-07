from dataclasses import dataclass
from typing import Protocol

from app.domain.workflows import WorkflowGraphData


class WorkflowVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class NodePosition:
    node_id: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class NodeActivity:
    node_id: str
    active_jobs: int
    queued_jobs: int
    waiting_jobs: int
    current_job_action: str | None
    task_id: str | None


class WorkflowDesigner(Protocol):
    async def get(self) -> WorkflowGraphData: ...
    async def replace(self, graph: WorkflowGraphData) -> WorkflowGraphData: ...
    async def save_positions(self, version: int, positions: tuple[NodePosition, ...]) -> None: ...
    async def activity(self) -> tuple[NodeActivity, ...]: ...
