import json
import uuid
from dataclasses import asdict, replace
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.model_validation import ModelValidationResult
from app.application.ports.workflow_designer import WorkflowVersionConflict
from app.db.models import (
    AIAgent,
    Role,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowRevision,
)
from app.domain.workflows import WorkflowEdgeData, WorkflowGraphData, WorkflowNodeData
from app.infrastructure.persistence.agent_runtime import resolve_agent_runtime_config

WORKFLOW_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _runtime_overrides(node: WorkflowNodeData) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if node.reasoning_effort != "default":
        overrides["reasoning_level"] = node.reasoning_effort.upper()
    if node.max_output_tokens is not None:
        overrides["max_output_tokens"] = node.max_output_tokens
    if node.temperature is not None:
        overrides["temperature"] = float(node.temperature)
    return overrides


def _validate_agent_runtime(node: WorkflowNodeData, agent: AIAgent, role: Role) -> None:
    if not node.enabled or not (agent.model or role.default_model):
        return
    try:
        resolve_agent_runtime_config(agent, role)
    except ValueError as exc:
        raise ValueError(f"Agent {agent.name} runtime is invalid: {exc}") from exc


def _normalized_node_state(
    item: WorkflowNodeData, current: WorkflowNode | None
) -> WorkflowNodeData:
    if current is None:
        return replace(
            item,
            integration_sync_status="IDLE",
            integration_sync_error=None,
            integration_last_synced_at=None,
            model_validation_status="NOT_CONFIGURED",
            model_validation_message=None,
            model_validated_at=None,
        )
    schedule_changed = (
        current.integration_mode != item.integration_mode
        or current.poll_interval_seconds != item.poll_interval_seconds
        or current.filter_assignee_id != item.filter_assignee_id
        or tuple(current.filter_state_ids or []) != item.filter_state_ids
        or tuple(current.integration_ids or []) != item.integration_ids
    )
    model_configuration_changed = (
        current.provider != item.provider
        or current.model != item.model
        or current.reasoning_effort != item.reasoning_effort
        or current.max_output_tokens != item.max_output_tokens
        or (float(current.temperature) if current.temperature is not None else None)
        != item.temperature
    )
    return replace(
        item,
        integration_sync_status="IDLE" if schedule_changed else current.integration_sync_status,
        integration_sync_error=None if schedule_changed else current.integration_sync_error,
        integration_last_synced_at=None if schedule_changed else current.integration_last_synced_at,
        model_validation_status=(
            "NOT_CONFIGURED" if model_configuration_changed else current.model_validation_status
        ),
        model_validation_message=(
            None if model_configuration_changed else current.model_validation_message
        ),
        model_validated_at=None if model_configuration_changed else current.model_validated_at,
    )


def default_graph(team_id: uuid.UUID = WORKFLOW_ID) -> WorkflowGraphData:
    nodes: tuple[WorkflowNodeData, ...] = (
        WorkflowNodeData(
            "10000000-0000-0000-0000-000000000001", "ORCHESTRATOR", "Orchestrator", 40, 200
        ),
        WorkflowNodeData("10000000-0000-0000-0000-000000000002", "INTAKE", "Intake", 300, 200),
        WorkflowNodeData("10000000-0000-0000-0000-000000000003", "THINKER", "Thinker", 560, 120),
        WorkflowNodeData("10000000-0000-0000-0000-000000000004", "EXECUTOR", "Executor", 820, 200),
        WorkflowNodeData("10000000-0000-0000-0000-000000000007", "TESTER", "Tester", 1080, 280),
        WorkflowNodeData("10000000-0000-0000-0000-000000000005", "REVIEWER", "Reviewer", 1300, 120),
        WorkflowNodeData(
            "10000000-0000-0000-0000-000000000006", "DELIVERER", "Deliverer", 1540, 200
        ),
    )
    if team_id != WORKFLOW_ID:
        nodes = tuple(
            replace(node, id=str(uuid.uuid5(team_id, f"node:{index}:{node.role}")))
            for index, node in enumerate(nodes)
        )
    by_role = {node.role: node for node in nodes}
    routes = (
        ("ORCHESTRATOR", "always", "INTAKE", "CLASSIFY_EVENT", None),
        ("INTAKE", "EVENT_INTERPRETED", "THINKER", "CREATE_PLAN", None),
        ("THINKER", "PLAN_READY", "EXECUTOR", "IMPLEMENT_PLAN", "PLAN_READY"),
        ("THINKER", "REPLAN_READY", "EXECUTOR", "IMPLEMENT_PLAN", "PLAN_READY"),
        ("EXECUTOR", "IMPLEMENTED", "TESTER", "RUN_VALIDATION", "LOCAL_VALIDATION"),
        ("EXECUTOR", "NEEDS_REPLAN", "THINKER", "REPLAN", "PLANNING"),
        ("EXECUTOR", "PLAN_MISMATCH", "THINKER", "REPLAN", "PLANNING"),
        ("TESTER", "TEST_PASS", "REVIEWER", "REVIEW_IMPLEMENTATION", "INTERNAL_REVIEW"),
        ("TESTER", "TEST_FAILED", "EXECUTOR", "FIX_TEST_FAILURES", "FIX_REQUIRED"),
        ("REVIEWER", "REVIEW_PASS", "DELIVERER", "PREPARE_DELIVERY", "WAITING_GITHUB"),
        ("REVIEWER", "PASS", "DELIVERER", "PREPARE_DELIVERY", "WAITING_GITHUB"),
        ("REVIEWER", "FAIL_ACTIONABLE", "EXECUTOR", "FIX_REVIEW_FINDINGS", "FIX_REQUIRED"),
        ("REVIEWER", "FAIL_ARCHITECTURAL", "THINKER", "REPLAN", "PLANNING"),
    )
    edges = tuple(
        WorkflowEdgeData(
            str(uuid.uuid5(team_id, f"route:{index}:{source}:{outcome}:{target}")),
            by_role[source].id,
            by_role[target].id,
            outcome,
            True,
            job_type,
            internal_state,
        )
        for index, (source, outcome, target, job_type, internal_state) in enumerate(routes)
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
            normalized_nodes.append(_normalized_node_state(item, current))
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
        self._add_revision(definition.id, definition.version, graph)
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
        entry = next(node for node in graph.nodes if node.role == "ORCHESTRATOR")
        definition = WorkflowDefinition(
            id=workflow_id,
            team_id=self._team_id,
            version=graph.version,
            entry_node_id=uuid.UUID(entry.id),
        )
        self._session.add(definition)
        await self._session.flush()
        await self._add_graph(graph, workflow_id)
        self._add_revision(workflow_id, graph.version, graph)
        await self._session.commit()

    def _add_revision(self, workflow_id: uuid.UUID, version: int, graph: WorkflowGraphData) -> None:
        self._session.add(
            WorkflowRevision(
                workflow_id=workflow_id,
                version=version,
                graph={
                    "version": version,
                    "nodes": [
                        json.loads(json.dumps(asdict(node), default=str)) for node in graph.nodes
                    ],
                    "edges": [
                        json.loads(json.dumps(asdict(edge), default=str)) for edge in graph.edges
                    ],
                },
            )
        )

    async def _add_graph(self, graph: WorkflowGraphData, workflow_id: uuid.UUID) -> None:
        roles = {
            item.name.upper(): item
            for item in (
                await self._session.scalars(select(Role).where(Role.archived_at.is_(None)))
            ).all()
        }
        roles_by_id = {item.id: item for item in roles.values()}
        existing_agents = {
            item.id: item
            for item in (
                await self._session.scalars(select(AIAgent).where(AIAgent.team_id == self._team_id))
            ).all()
        }
        agent_ids: dict[str, uuid.UUID | None] = {}
        for node in graph.nodes:
            agent = existing_agents.get(uuid.UUID(node.agent_id)) if node.agent_id else None
            runtime_overrides = _runtime_overrides(node)
            if agent is None and node.role in roles:
                agent = AIAgent(
                    team_id=self._team_id,
                    role_id=roles[node.role].id,
                    name=node.label,
                    provider=node.provider or None,
                    model=node.model or None,
                    custom_instructions=node.system_prompt,
                    runtime_overrides=runtime_overrides,
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
                if agent.runtime_overrides != runtime_overrides:
                    agent.runtime_overrides = runtime_overrides
                    agent.config_version += 1
            if agent is not None and node.enabled:
                role = roles_by_id.get(agent.role_id)
                if role is None:
                    raise ValueError(f"Agent {agent.name} has no active Role")
                _validate_agent_runtime(node, agent, role)
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
                node_type=node.node_type,
                system_node_type=node.system_node_type,
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
                job_type=edge.job_type,
                internal_task_state=edge.internal_task_state,
                external_status_key=edge.external_status_key,
                priority_override=edge.priority_override,
                configuration=edge.configuration or {},
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
                    node.node_type,
                    node.system_node_type,
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
                    edge.job_type,
                    edge.internal_task_state,
                    edge.external_status_key,
                    edge.priority_override,
                    edge.configuration,
                )
                for edge in edges
            ),
        )
