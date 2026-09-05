import uuid
from dataclasses import replace
from datetime import datetime
from itertools import pairwise

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.model_validation import ModelValidationResult
from app.application.ports.workflow_designer import WorkflowVersionConflict
from app.db.models import AIAgent, Role, WorkflowDefinition, WorkflowEdge, WorkflowNode
from app.domain.workflows import WorkflowEdgeData, WorkflowGraphData, WorkflowNodeData

WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def default_graph(team_id: uuid.UUID = WORKFLOW_ID) -> WorkflowGraphData:
    nodes: tuple[WorkflowNodeData, ...] = (
        WorkflowNodeData(
            "10000000-0000-0000-0000-000000000001", "ORCHESTRATOR", "Orchestrator", 40, 200
        ),
        WorkflowNodeData("10000000-0000-0000-0000-000000000002", "INTAKE", "Intake", 300, 200),
        WorkflowNodeData("10000000-0000-0000-0000-000000000003", "THINKER", "Thinker", 560, 120),
        WorkflowNodeData("10000000-0000-0000-0000-000000000004", "EXECUTOR", "Executor", 820, 200),
        WorkflowNodeData("10000000-0000-0000-0000-000000000005", "REVIEWER", "Reviewer", 1080, 120),
        WorkflowNodeData("10000000-0000-0000-0000-000000000007", "TESTER", "Tester", 1210, 280),
        WorkflowNodeData(
            "10000000-0000-0000-0000-000000000006", "DELIVERER", "Deliverer", 1470, 200
        ),
    )
    if team_id != WORKFLOW_ID:
        nodes = tuple(
            replace(node, id=str(uuid.uuid5(team_id, f"node:{index}:{node.role}")))
            for index, node in enumerate(nodes)
        )
    edges = tuple(
        WorkflowEdgeData(
            (
                f"20000000-0000-0000-0000-00000000000{index}"
                if team_id == WORKFLOW_ID
                else str(uuid.uuid5(team_id, f"edge:{index}:{source.role}:{target.role}"))
            ),
            source.id,
            target.id,
        )
        for index, (source, target) in enumerate(pairwise(nodes), start=1)
    )
    return WorkflowGraphData(1, nodes, edges)


class SqlAlchemyWorkflowDesigner:
    def __init__(self, session: AsyncSession, team_id: uuid.UUID = WORKFLOW_ID) -> None:
        self._session = session
        self._team_id = team_id

    async def _definition(self, *, lock: bool = False) -> WorkflowDefinition | None:
        statement = select(WorkflowDefinition).where(WorkflowDefinition.team_id == self._team_id)
        if lock:
            statement = statement.with_for_update()
        definition = await self._session.scalar(statement)
        if definition is None and self._team_id == WORKFLOW_ID:
            definition = await self._session.get(WorkflowDefinition, WORKFLOW_ID)
            if definition is not None and definition.team_id is None:
                definition.team_id = self._team_id
        return definition

    async def get(self) -> WorkflowGraphData:
        definition = await self._definition()
        if definition is None:
            graph = default_graph(self._team_id)
            await self._persist_new(graph)
            return graph
        return await self._read(definition.version)

    async def replace(self, graph: WorkflowGraphData) -> WorkflowGraphData:
        definition = await self._definition(lock=True)
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
        current_nodes = {
            str(node.id): node
            for node in (
                await self._session.scalars(
                    select(WorkflowNode).where(WorkflowNode.workflow_id == definition.id)
                )
            ).all()
        }
        normalized_nodes: list[WorkflowNodeData] = []
        for item in graph.nodes:
            current = current_nodes.get(item.id)
            schedule_changed = current is None or (
                current.integration_mode != item.integration_mode
                or current.poll_interval_seconds != item.poll_interval_seconds
                or current.filter_assignee_id != item.filter_assignee_id
                or tuple(current.filter_state_ids or []) != item.filter_state_ids
                or tuple(current.integration_ids or []) != item.integration_ids
            )
            if current is None or schedule_changed:
                sync_status = "IDLE"
                sync_error = None
                last_synced_at = None
            else:
                sync_status = current.integration_sync_status
                sync_error = current.integration_sync_error
                last_synced_at = current.integration_last_synced_at
            normalized_nodes.append(
                replace(
                    item,
                    integration_sync_status=sync_status,
                    integration_sync_error=sync_error,
                    integration_last_synced_at=last_synced_at,
                )
            )
        graph = WorkflowGraphData(graph.version, tuple(normalized_nodes), graph.edges)
        await self._session.execute(
            delete(WorkflowEdge).where(WorkflowEdge.workflow_id == definition.id)
        )
        await self._session.execute(
            delete(WorkflowNode).where(WorkflowNode.workflow_id == definition.id)
        )
        await self._session.flush()
        definition.version += 1
        await self._add_graph(graph, definition.id)
        await self._session.commit()
        return WorkflowGraphData(definition.version, graph.nodes, graph.edges)

    async def node_model(self, node_id: str) -> tuple[str, str] | None:
        node = await self._session.get(WorkflowNode, uuid.UUID(node_id))
        definition = await self._definition()
        if node is None or definition is None or node.workflow_id != definition.id:
            return None
        return node.provider, node.model

    async def record_model_validation(
        self, node_id: str, result: ModelValidationResult, validated_at: datetime
    ) -> None:
        node = await self._session.get(WorkflowNode, uuid.UUID(node_id))
        definition = await self._definition()
        if node is None or definition is None or node.workflow_id != definition.id:
            raise ValueError("Workflow node not found")
        node.model_validation_status = result.status
        node.model_validation_message = result.message
        node.model_validated_at = validated_at
        await self._session.commit()

    async def _persist_new(self, graph: WorkflowGraphData) -> None:
        workflow_id = WORKFLOW_ID if self._team_id == WORKFLOW_ID else uuid.uuid4()
        self._session.add(
            WorkflowDefinition(id=workflow_id, team_id=self._team_id, version=graph.version)
        )
        await self._session.flush()
        await self._add_graph(graph, workflow_id)
        await self._session.commit()

    async def _add_graph(self, graph: WorkflowGraphData, workflow_id: uuid.UUID) -> None:
        roles = {
            item.name.upper(): item
            for item in (
                await self._session.scalars(select(Role).where(Role.archived_at.is_(None)))
            ).all()
        }
        existing_agents = {
            item.id: item
            for item in (
                await self._session.scalars(select(AIAgent).where(AIAgent.team_id == self._team_id))
            ).all()
        }
        agent_ids: dict[str, uuid.UUID | None] = {}
        for node in graph.nodes:
            agent = existing_agents.get(uuid.UUID(node.agent_id)) if node.agent_id else None
            if agent is None and node.role in roles:
                agent = AIAgent(
                    team_id=self._team_id,
                    role_id=roles[node.role].id,
                    name=node.label,
                    provider=node.provider or None,
                    model=node.model or None,
                    custom_instructions=node.system_prompt,
                    enabled=node.enabled,
                )
                self._session.add(agent)
                await self._session.flush()
            elif agent is not None:
                agent.name = node.label
                agent.provider = node.provider or None
                agent.model = node.model or None
                agent.custom_instructions = node.system_prompt
                agent.enabled = node.enabled
            agent_ids[node.id] = agent.id if agent else None
        self._session.add_all(
            WorkflowNode(
                id=uuid.UUID(node.id),
                workflow_id=workflow_id,
                agent_id=agent_ids[node.id],
                role=node.role,
                label=node.label,
                position_x=node.position_x,
                position_y=node.position_y,
                enabled=node.enabled,
                activation_policy=node.activation_policy,
                batch_window_seconds=node.batch_window_seconds,
                integration_ids=list(node.integration_ids),
                repository_ids=list(node.repository_ids),
                provider=node.provider,
                model=node.model,
                system_prompt=node.system_prompt,
                model_validation_status=node.model_validation_status,
                model_validation_message=node.model_validation_message,
                model_validated_at=node.model_validated_at,
                integration_mode=node.integration_mode,
                poll_interval_seconds=node.poll_interval_seconds,
                filter_assignee_id=node.filter_assignee_id,
                filter_state_ids=list(node.filter_state_ids),
                integration_sync_status=node.integration_sync_status,
                integration_sync_error=node.integration_sync_error,
                integration_last_synced_at=node.integration_last_synced_at,
                reasoning_effort=node.reasoning_effort,
                max_output_tokens=node.max_output_tokens,
                temperature=node.temperature,
                timeout_minutes=node.timeout_minutes,
                max_retries=node.max_retries,
                max_review_cycles=node.max_review_cycles,
                context_depth=node.context_depth,
                rag_retrieval_depth=node.rag_retrieval_depth,
                fallback_provider=node.fallback_provider,
                fallback_model=node.fallback_model,
            )
            for node in graph.nodes
        )
        await self._session.flush()
        self._session.add_all(
            WorkflowEdge(
                id=uuid.UUID(edge.id),
                workflow_id=workflow_id,
                source_node_id=uuid.UUID(edge.source_node_id),
                target_node_id=uuid.UUID(edge.target_node_id),
                outcome=edge.outcome,
                required=edge.required,
            )
            for edge in graph.edges
        )

    async def _read(self, version: int) -> WorkflowGraphData:
        definition = await self._definition()
        if definition is None:
            raise RuntimeError("Workflow definition disappeared")
        nodes = list(
            (
                await self._session.scalars(
                    select(WorkflowNode).where(WorkflowNode.workflow_id == definition.id)
                )
            ).all()
        )
        edges = list(
            (
                await self._session.scalars(
                    select(WorkflowEdge).where(WorkflowEdge.workflow_id == definition.id)
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
                    tuple(node.integration_ids or []),
                    tuple(node.repository_ids or []),
                    node.provider,
                    node.model,
                    node.system_prompt,
                    node.model_validation_status,
                    node.model_validation_message,
                    node.model_validated_at,
                    node.integration_mode,
                    node.poll_interval_seconds,
                    node.filter_assignee_id,
                    tuple(node.filter_state_ids or []),
                    node.integration_sync_status,
                    node.integration_sync_error,
                    node.integration_last_synced_at,
                    node.reasoning_effort,
                    node.max_output_tokens,
                    float(node.temperature) if node.temperature is not None else None,
                    node.timeout_minutes,
                    node.max_retries,
                    node.max_review_cycles,
                    node.context_depth,
                    node.rag_retrieval_depth,
                    node.fallback_provider,
                    node.fallback_model,
                    str(node.agent_id) if node.agent_id else None,
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
