import math

from app.application.ports.workflow_designer import NodeActivity, NodePosition, WorkflowDesigner
from app.domain.workflows import WorkflowGraphData, validate_workflow_graph


class DesignWorkflow:
    def __init__(self, designer: WorkflowDesigner) -> None:
        self._designer = designer

    async def get(self) -> WorkflowGraphData:
        return await self._designer.get()

    async def replace(self, graph: WorkflowGraphData) -> WorkflowGraphData:
        validate_workflow_graph(graph)
        return await self._designer.replace(graph)

    async def save_positions(self, version: int, positions: tuple[NodePosition, ...]) -> None:
        if len({position.node_id for position in positions}) != len(positions):
            raise ValueError("Node positions must be unique")
        if any(not math.isfinite(p.x) or not math.isfinite(p.y) for p in positions):
            raise ValueError("Node positions must be finite")
        await self._designer.save_positions(version, positions)

    async def activity(self) -> tuple[NodeActivity, ...]:
        return await self._designer.activity()
