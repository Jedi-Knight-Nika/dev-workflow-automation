from dataclasses import dataclass
from datetime import datetime

SYSTEM_ROLES = frozenset({"ORCHESTRATOR", "DELIVERER"})
AGENT_ROLES = frozenset({"INTAKE", "THINKER", "EXECUTOR", "REVIEWER", "TESTER"})
ALLOWED_ROLES = SYSTEM_ROLES | AGENT_ROLES
ALLOWED_OUTCOMES = frozenset({"success", "failure", "changes_requested", "always"})
ALLOWED_ACTIVATION_POLICIES = frozenset({"any", "all", "required", "manual", "batch"})
ALLOWED_MODEL_STATUSES = frozenset(
    {"NOT_CONFIGURED", "UNVERIFIED", "AVAILABLE", "MODEL_NOT_FOUND", "UNAUTHORIZED", "ERROR"}
)


@dataclass(frozen=True, slots=True)
class WorkflowNodeData:
    id: str
    role: str
    label: str
    position_x: float
    position_y: float
    enabled: bool = True
    activation_policy: str = "any"
    batch_window_seconds: int = 0
    integration_ids: tuple[str, ...] = ()
    repository_ids: tuple[str, ...] = ()
    provider: str = "openai"
    model: str = ""
    system_prompt: str = ""
    model_validation_status: str = "NOT_CONFIGURED"
    model_validation_message: str | None = None
    model_validated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WorkflowEdgeData:
    id: str
    source_node_id: str
    target_node_id: str
    outcome: str = "success"
    required: bool = True


@dataclass(frozen=True, slots=True)
class WorkflowGraphData:
    version: int
    nodes: tuple[WorkflowNodeData, ...]
    edges: tuple[WorkflowEdgeData, ...]


def validate_workflow_graph(graph: WorkflowGraphData) -> None:
    if not graph.nodes:
        raise ValueError("Workflow must contain nodes")
    node_ids = [node.id for node in graph.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("Workflow node IDs must be unique")
    edge_ids = [edge.id for edge in graph.edges]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError("Workflow edge IDs must be unique")
    roles = [node.role for node in graph.nodes]
    unknown = set(roles) - ALLOWED_ROLES
    if unknown:
        raise ValueError(f"Unsupported workflow roles: {', '.join(sorted(unknown))}")
    for protected in SYSTEM_ROLES:
        if roles.count(protected) != 1:
            raise ValueError(f"Workflow requires exactly one {protected} node")
    for node in graph.nodes:
        if not node.label.strip():
            raise ValueError("Workflow node nickname cannot be blank")
        if len(node.integration_ids) != len(set(node.integration_ids)):
            raise ValueError("Workflow node integrations must be unique")
        if len(node.repository_ids) != len(set(node.repository_ids)):
            raise ValueError("Workflow node repositories must be unique")
        if node.provider not in {"openai", "anthropic", "google"}:
            raise ValueError(f"Unsupported AI provider: {node.provider}")
        if len(node.model) > 255:
            raise ValueError("Workflow node model ID is too long")
        if len(node.system_prompt) > 100_000:
            raise ValueError("Workflow node system prompt is too long")
        if node.model_validation_status not in ALLOWED_MODEL_STATUSES:
            raise ValueError("Unsupported model validation status")
        if node.activation_policy not in ALLOWED_ACTIVATION_POLICIES:
            raise ValueError(f"Unsupported activation policy: {node.activation_policy}")
        if not 0 <= node.batch_window_seconds <= 300:
            raise ValueError("Batch window must be between 0 and 300 seconds")
    known = set(node_ids)
    outgoing: dict[str, set[str]] = {node_id: set() for node_id in known}
    for edge in graph.edges:
        if edge.source_node_id not in known or edge.target_node_id not in known:
            raise ValueError("Workflow edge references a missing node")
        if edge.source_node_id == edge.target_node_id:
            raise ValueError("Workflow nodes cannot connect to themselves")
        if edge.outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"Unsupported edge outcome: {edge.outcome}")
        outgoing[edge.source_node_id].add(edge.target_node_id)
    start = next(node.id for node in graph.nodes if node.role == "ORCHESTRATOR")
    finish = next(node.id for node in graph.nodes if node.role == "DELIVERER")
    reachable = {start}
    pending = [start]
    while pending:
        current = pending.pop()
        for target in outgoing[current] - reachable:
            reachable.add(target)
            pending.append(target)
    enabled = {node.id for node in graph.nodes if node.enabled}
    unreachable = enabled - reachable
    if unreachable:
        raise ValueError("Every enabled node must be reachable from Orchestrator")
    if finish not in reachable:
        raise ValueError("Workflow must contain a path to Deliverer")
