import pytest

from app.domain.workflows import (
    WorkflowEdgeData,
    WorkflowGraphData,
    WorkflowNodeData,
    WorkflowRouteNotFound,
    resolve_route,
)


def graph(*edges: WorkflowEdgeData) -> WorkflowGraphData:
    return WorkflowGraphData(
        4,
        (
            WorkflowNodeData("tester", "TESTER", "QA", 0, 0),
            WorkflowNodeData("executor", "EXECUTOR", "Builder", 1, 0),
            WorkflowNodeData("reviewer", "REVIEWER", "Reviewer", 2, 0),
        ),
        edges,
    )


def test_resolves_exact_outcome_before_fallback() -> None:
    value = graph(
        WorkflowEdgeData("fallback", "tester", "reviewer", "always"),
        WorkflowEdgeData(
            "failed", "tester", "executor", "TEST_FAILED", job_type="FIX_TEST_FAILURES"
        ),
    )
    decision = resolve_route(value, "tester", "TEST_FAILED")
    assert decision.target.id == "executor"
    assert decision.edge.job_type == "FIX_TEST_FAILURES"


def test_resolves_explicit_fallback_for_unmatched_result() -> None:
    value = graph(WorkflowEdgeData("fallback", "tester", "reviewer", "always"))
    assert resolve_route(value, "tester", "UNKNOWN_RESULT").target.id == "reviewer"


def test_rejects_ambiguous_or_missing_routes() -> None:
    ambiguous = graph(
        WorkflowEdgeData("one", "tester", "executor", "TEST_FAILED"),
        WorkflowEdgeData("two", "tester", "reviewer", "TEST_FAILED"),
    )
    with pytest.raises(WorkflowRouteNotFound, match="multiple routes"):
        resolve_route(ambiguous, "tester", "TEST_FAILED")
    with pytest.raises(WorkflowRouteNotFound, match="No route"):
        resolve_route(graph(), "tester", "TEST_PASS")
