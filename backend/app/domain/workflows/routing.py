from dataclasses import dataclass

from app.domain.workflows.graph import WorkflowEdgeData, WorkflowGraphData, WorkflowNodeData


@dataclass(frozen=True, slots=True)
class RouteDecision:
    source: WorkflowNodeData
    edge: WorkflowEdgeData
    target: WorkflowNodeData


class WorkflowRouteNotFound(ValueError):
    pass


def resolve_route_edge(
    edges: tuple[WorkflowEdgeData, ...], source_node_id: str, result_type: str
) -> WorkflowEdgeData:
    """Resolve the unique exact edge, or the unique explicit fallback edge."""
    candidates = [edge for edge in edges if edge.source_node_id == source_node_id]
    exact = [edge for edge in candidates if edge.outcome == result_type]
    fallback = [edge for edge in candidates if edge.outcome == "always"]
    matches = exact or fallback
    if not matches:
        raise WorkflowRouteNotFound(f"No route for result {result_type}")
    if len(matches) > 1:
        raise WorkflowRouteNotFound(f"Workflow has multiple routes for result {result_type}")
    return matches[0]


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
