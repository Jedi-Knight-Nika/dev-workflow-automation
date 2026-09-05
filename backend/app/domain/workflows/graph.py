from dataclasses import dataclass

SYSTEM_ROLES = frozenset({"ORCHESTRATOR", "DELIVERER"})
AGENT_ROLES = frozenset({"INTAKE", "THINKER", "EXECUTOR", "REVIEWER", "TESTER"})
ALLOWED_ROLES = SYSTEM_ROLES | AGENT_ROLES
ALLOWED_OUTCOMES = frozenset({"success", "failure", "changes_requested", "always"})
ALLOWED_ACTIVATION_POLICIES = frozenset({"any", "all", "required", "manual", "batch"})


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
