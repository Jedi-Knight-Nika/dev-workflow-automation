from dataclasses import dataclass

from app.domain.workflows.graph import WorkflowEdgeData, WorkflowGraphData, WorkflowNodeData


@dataclass(frozen=True, slots=True)
class RouteDecision:
    source: WorkflowNodeData
    edge: WorkflowEdgeData
    target: WorkflowNodeData


class WorkflowRouteNotFound(ValueError):
    pass


def resolve_route(graph: WorkflowGraphData, source_node_id: str, result_type: str) -> RouteDecision:
    """Resolve one deterministic outcome route, with `always` as the explicit fallback."""
    nodes = {node.id: node for node in graph.nodes}
    source = nodes.get(source_node_id)
    if source is None:
        raise WorkflowRouteNotFound("Current workflow node no longer exists")
    if not source.enabled:
        raise WorkflowRouteNotFound("Current workflow node is disabled")
    candidates = [edge for edge in graph.edges if edge.source_node_id == source_node_id]
    exact = [edge for edge in candidates if edge.outcome == result_type]
    fallback = [edge for edge in candidates if edge.outcome == "always"]
    matches = exact or fallback
    if not matches:
        raise WorkflowRouteNotFound(
            f"No route from {source.label} for result {result_type}; human attention is required"
        )
    if len(matches) > 1:
        raise WorkflowRouteNotFound(
            f"Workflow has multiple routes from {source.label} for result {result_type}"
        )
    edge = matches[0]
    target = nodes.get(edge.target_node_id)
    if target is None or not target.enabled:
        raise WorkflowRouteNotFound("Configured workflow destination is unavailable")
    return RouteDecision(source, edge, target)
