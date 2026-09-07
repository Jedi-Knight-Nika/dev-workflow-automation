from dataclasses import dataclass

from app.domain.workflows.graph import (
    WorkflowEdgeData,
    WorkflowGraphData,
    WorkflowNodeData,
    connection_kind,
)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    source: WorkflowNodeData
    edge: WorkflowEdgeData
    target: WorkflowNodeData


class WorkflowRouteNotFound(ValueError):
    pass


def route_outcomes(result_type: str) -> tuple[str, ...]:
    """Priority-ordered aliases. Unknown/custom results never imply success."""
    if result_type in {"EVENT_INTERPRETED", "PLAN_READY", "IMPLEMENTED", "TEST_PASS", "PASS"}:
        return (result_type, "success", "always")
    if result_type in {
        "TEST_FAILED",
        "FAIL_ACTIONABLE",
        "FAIL_ARCHITECTURAL",
        "PLAN_MISMATCH",
        "NEEDS_REPLAN",
    }:
        return (result_type, "changes_requested", "failure", "always")
    if result_type in {
        "BLOCKED",
        "NEEDS_HUMAN",
        "NEEDS_CONTEXT",
        "UNCERTAIN",
        "TEST_ENVIRONMENT_FAILURE",
        "TEST_INCOMPLETE",
    }:
        return (result_type, "failure", "always")
    return (result_type, "always")


def resolve_route_edge(
    edges: tuple[WorkflowEdgeData, ...], source_node_id: str, result_type: str
) -> WorkflowEdgeData:
    """Resolve exact result, known outcome family, then explicit fallback."""
    candidates = [
        edge
        for edge in edges
        if edge.source_node_id == source_node_id and connection_kind(edge) == "handoff"
    ]
    for outcome in route_outcomes(result_type):
        matches = [edge for edge in candidates if edge.outcome == outcome]
        if len(matches) > 1:
            raise WorkflowRouteNotFound(f"Workflow has multiple routes for result {result_type}")
        if matches:
            return matches[0]
    raise WorkflowRouteNotFound(f"No route for result {result_type}")


def resolve_route(graph: WorkflowGraphData, source_node_id: str, result_type: str) -> RouteDecision:
    """Resolve one deterministic outcome route, with `always` as the explicit fallback."""
    nodes = {node.id: node for node in graph.nodes}
    source = nodes.get(source_node_id)
    if source is None:
        raise WorkflowRouteNotFound("Current workflow node no longer exists")
    if not source.enabled:
        raise WorkflowRouteNotFound("Current workflow node is disabled")
    try:
        edge = resolve_route_edge(graph.edges, source_node_id, result_type)
    except WorkflowRouteNotFound as exc:
        raise WorkflowRouteNotFound(f"{exc} from {source.label}") from exc
    target = nodes.get(edge.target_node_id)
    if target is None or not target.enabled:
        raise WorkflowRouteNotFound("Configured workflow destination is unavailable")
    return RouteDecision(source, edge, target)


def resolve_handoff(
    graph: WorkflowGraphData, source_node_id: str, result_type: str
) -> tuple[RouteDecision, ...]:
    """Pass a typed result through deterministic controllers, without spawning an AI job there."""
    path: list[RouteDecision] = []
    visited = {source_node_id}
    while True:
        decision = resolve_route(graph, source_node_id, result_type)
        path.append(decision)
        if decision.target.role != "ORCHESTRATOR":
            return tuple(path)
        if decision.target.id in visited:
            raise WorkflowRouteNotFound("Workflow controller connections form a routing cycle")
        visited.add(decision.target.id)
        source_node_id = decision.target.id
