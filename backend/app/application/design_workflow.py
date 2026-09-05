from app.application.ports.workflow_designer import WorkflowDesigner
from app.domain.workflows import WorkflowGraphData, validate_workflow_graph


class DesignWorkflow:
    def __init__(self, designer: WorkflowDesigner) -> None:
        self._designer = designer

    async def get(self) -> WorkflowGraphData:
        return await self._designer.get()

    async def replace(self, graph: WorkflowGraphData) -> WorkflowGraphData:
        validate_workflow_graph(graph)
        return await self._designer.replace(graph)
