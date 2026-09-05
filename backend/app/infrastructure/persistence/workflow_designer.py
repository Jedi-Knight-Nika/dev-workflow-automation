import uuid
from itertools import pairwise

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.workflow_designer import WorkflowVersionConflict
from app.db.models import WorkflowDefinition, WorkflowEdge, WorkflowNode
from app.domain.workflows import WorkflowEdgeData, WorkflowGraphData, WorkflowNodeData

WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def default_graph() -> WorkflowGraphData:
    nodes = (
        WorkflowNodeData(
            "10000000-0000-0000-0000-000000000001", "ORCHESTRATOR", "Orchestrator", 40, 200
        ),
        WorkflowNodeData("10000000-0000-0000-0000-000000000002", "INTAKE", "Intake", 300, 200),
        WorkflowNodeData("10000000-0000-0000-0000-000000000003", "THINKER", "Thinker", 560, 120),
        WorkflowNodeData("10000000-0000-0000-0000-000000000004", "EXECUTOR", "Executor", 820, 200),
        WorkflowNodeData("10000000-0000-0000-0000-000000000005", "REVIEWER", "Reviewer", 1080, 120),
        WorkflowNodeData(
            "10000000-0000-0000-0000-000000000006", "DELIVERER", "Deliverer", 1340, 200
        ),
    )
    edges = tuple(
        WorkflowEdgeData(f"20000000-0000-0000-0000-00000000000{index}", source.id, target.id)
        for index, (source, target) in enumerate(pairwise(nodes), start=1)
    )
    return WorkflowGraphData(1, nodes, edges)


class SqlAlchemyWorkflowDesigner:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> WorkflowGraphData:
        definition = await self._session.get(WorkflowDefinition, WORKFLOW_ID)
        if definition is None:
            graph = default_graph()
            await self._persist_new(graph)
            return graph
        return await self._read(definition.version)

    async def replace(self, graph: WorkflowGraphData) -> WorkflowGraphData:
        definition = await self._session.scalar(
            select(WorkflowDefinition).where(WorkflowDefinition.id == WORKFLOW_ID).with_for_update()
        )
        if definition is None:
            if graph.version != 0:
                raise WorkflowVersionConflict("Workflow was created by another editor")
            created = WorkflowGraphData(1, graph.nodes, graph.edges)
            await self._persist_new(created)
            return created
        if definition.version != graph.version:
            raise WorkflowVersionConflict(
                f"Workflow changed from version {graph.version} to {definition.version}; reload it"
            )
        await self._session.execute(
            delete(WorkflowEdge).where(WorkflowEdge.workflow_id == WORKFLOW_ID)
        )
        await self._session.execute(
            delete(WorkflowNode).where(WorkflowNode.workflow_id == WORKFLOW_ID)
        )
        await self._session.flush()
        definition.version += 1
        await self._add_graph(graph)
        await self._session.commit()
        return WorkflowGraphData(definition.version, graph.nodes, graph.edges)

    async def _persist_new(self, graph: WorkflowGraphData) -> None:
        self._session.add(WorkflowDefinition(id=WORKFLOW_ID, version=graph.version))
        await self._session.flush()
        await self._add_graph(graph)
        await self._session.commit()

    async def _add_graph(self, graph: WorkflowGraphData) -> None:
        self._session.add_all(
            WorkflowNode(
                id=uuid.UUID(node.id),
                workflow_id=WORKFLOW_ID,
                role=node.role,
                label=node.label,
                position_x=node.position_x,
                position_y=node.position_y,
                enabled=node.enabled,
                activation_policy=node.activation_policy,
                batch_window_seconds=node.batch_window_seconds,
            )
            for node in graph.nodes
        )
        await self._session.flush()
        self._session.add_all(
            WorkflowEdge(
                id=uuid.UUID(edge.id),
                workflow_id=WORKFLOW_ID,
                source_node_id=uuid.UUID(edge.source_node_id),
                target_node_id=uuid.UUID(edge.target_node_id),
                outcome=edge.outcome,
                required=edge.required,
            )
            for edge in graph.edges
        )

    async def _read(self, version: int) -> WorkflowGraphData:
        nodes = list(
            (
                await self._session.scalars(
                    select(WorkflowNode).where(WorkflowNode.workflow_id == WORKFLOW_ID)
                )
            ).all()
        )
        edges = list(
            (
                await self._session.scalars(
                    select(WorkflowEdge).where(WorkflowEdge.workflow_id == WORKFLOW_ID)
                )
            ).all()
        )
        return WorkflowGraphData(
            version,
            tuple(
                WorkflowNodeData(
                    str(node.id),
                    node.role,
                    node.label,
                    float(node.position_x),
                    float(node.position_y),
                    node.enabled,
                    node.activation_policy,
                    node.batch_window_seconds,
                )
                for node in nodes
            ),
            tuple(
                WorkflowEdgeData(
                    str(edge.id),
                    str(edge.source_node_id),
                    str(edge.target_node_id),
                    edge.outcome,
                    edge.required,
                )
                for edge in edges
            ),
        )
