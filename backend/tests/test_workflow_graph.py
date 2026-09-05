import pytest

from app.domain.workflows import (
    WorkflowEdgeData,
    WorkflowGraphData,
    WorkflowNodeData,
    validate_workflow_graph,
)


def valid_graph() -> WorkflowGraphData:
    return WorkflowGraphData(
        1,
        (
            WorkflowNodeData("orchestrator", "ORCHESTRATOR", "Orchestrator", 0, 0),
            WorkflowNodeData("executor", "EXECUTOR", "Executor", 100, 0),
            WorkflowNodeData("reviewer", "REVIEWER", "Reviewer", 200, 0, activation_policy="all"),
            WorkflowNodeData("deliverer", "DELIVERER", "Deliverer", 300, 0),
        ),
        (
            WorkflowEdgeData("one", "orchestrator", "executor"),
            WorkflowEdgeData("two", "executor", "reviewer"),
            WorkflowEdgeData("three", "reviewer", "deliverer"),
            WorkflowEdgeData("repair", "reviewer", "executor", "changes_requested"),
        ),
    )


def test_valid_workflow_supports_fan_routes_and_explicit_repair_loop() -> None:
    validate_workflow_graph(valid_graph())


def test_workflow_rejects_unreachable_enabled_node() -> None:
    graph = valid_graph()
    graph = WorkflowGraphData(
        graph.version,
        graph.nodes + (WorkflowNodeData("tester", "TESTER", "Tester", 200, 100),),
        graph.edges,
    )
    with pytest.raises(ValueError, match="reachable"):
        validate_workflow_graph(graph)


def test_workflow_rejects_missing_protected_stage() -> None:
    graph = valid_graph()
    graph = WorkflowGraphData(
        graph.version,
        tuple(node for node in graph.nodes if node.role != "DELIVERER"),
        graph.edges,
    )
    with pytest.raises(ValueError, match="DELIVERER"):
        validate_workflow_graph(graph)


def test_workflow_rejects_unknown_activation_policy() -> None:
    graph = valid_graph()
    changed = tuple(
        WorkflowNodeData(
            node.id,
            node.role,
            node.label,
            node.position_x,
            node.position_y,
            node.enabled,
            "sometimes" if node.role == "EXECUTOR" else node.activation_policy,
        )
        for node in graph.nodes
    )
    with pytest.raises(ValueError, match="activation policy"):
        validate_workflow_graph(WorkflowGraphData(graph.version, changed, graph.edges))
