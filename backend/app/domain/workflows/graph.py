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
ALLOWED_INTEGRATION_MODES = frozenset({"webhook", "poll", "hybrid", "manual"})


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
    integration_mode: str = "webhook"
    poll_interval_seconds: int = 300
    filter_assignee_id: str = ""
    filter_state_ids: tuple[str, ...] = ()
    integration_sync_status: str = "IDLE"
    integration_sync_error: str | None = None
    integration_last_synced_at: datetime | None = None
    reasoning_effort: str = "default"
    max_output_tokens: int | None = None
    temperature: float | None = None
    timeout_minutes: int = 60
    max_retries: int = 2
    max_review_cycles: int = 3
    context_depth: str = "normal"
    rag_retrieval_depth: str = "normal"
    fallback_provider: str | None = None
    fallback_model: str | None = None
    agent_id: str | None = None


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
        if node.integration_mode not in ALLOWED_INTEGRATION_MODES:
            raise ValueError("Unsupported integration trigger mode")
        if not 60 <= node.poll_interval_seconds <= 86_400:
            raise ValueError("Polling interval must be between 60 seconds and 24 hours")
        if len(node.filter_state_ids) != len(set(node.filter_state_ids)):
            raise ValueError("Workflow node state filters must be unique")
        if node.activation_policy not in ALLOWED_ACTIVATION_POLICIES:
            raise ValueError(f"Unsupported activation policy: {node.activation_policy}")
        if not 0 <= node.batch_window_seconds <= 300:
            raise ValueError("Batch window must be between 0 and 300 seconds")
        if node.reasoning_effort not in {"default", "low", "medium", "high", "max"}:
            raise ValueError("Unsupported reasoning effort")
        if node.max_output_tokens is not None and not 256 <= node.max_output_tokens <= 200_000:
            raise ValueError("Max output tokens must be between 256 and 200000")
        if node.temperature is not None and not 0 <= node.temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2")
        if not 1 <= node.timeout_minutes <= 720:
            raise ValueError("Timeout must be between 1 and 720 minutes")
        if not 0 <= node.max_retries <= 10 or not 0 <= node.max_review_cycles <= 20:
            raise ValueError("Retry and review limits are outside the supported range")
        if node.context_depth not in {"low", "normal", "deep"}:
            raise ValueError("Unsupported context depth")
        if node.rag_retrieval_depth not in {"low", "normal", "deep"}:
            raise ValueError("Unsupported RAG retrieval depth")
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
