import pytest

from app.domain.workflows import (
    WorkflowEdgeData,
    WorkflowGraphData,
    WorkflowNodeData,
    WorkflowRouteNotFound,
    resolve_route,
)
from app.domain.workflows.graph import consultation_targets
from app.domain.workflows.routing import resolve_handoff
from app.infrastructure.persistence.workflow_routing import _stable_progress_evidence


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


@pytest.mark.parametrize(
    "result", ["PLAN_READY", "IMPLEMENTED", "TEST_PASS", "PASS", "EVENT_INTERPRETED"]
)
def test_generic_success_connections_match_typed_results(result: str) -> None:
    value = graph(WorkflowEdgeData("success", "tester", "reviewer", "success"))
    assert resolve_route(value, "tester", result).target.id == "reviewer"


def test_rework_connection_outranks_general_failure() -> None:
    value = graph(
        WorkflowEdgeData("failure", "tester", "reviewer", "failure"),
        WorkflowEdgeData("rework", "tester", "executor", "changes_requested"),
        WorkflowEdgeData("exact", "tester", "reviewer", "TEST_FAILED"),
    )
    assert resolve_route(value, "tester", "TEST_FAILED").edge.id == "exact"
    assert resolve_route(value, "tester", "FAIL_ACTIONABLE").edge.id == "rework"
    assert resolve_route(value, "tester", "NEEDS_HUMAN").edge.id == "failure"


def test_unknown_or_blocked_result_never_follows_success() -> None:
    value = graph(WorkflowEdgeData("success", "tester", "reviewer", "success"))
    for result in ("UNRECOGNIZED", "BLOCKED", "NEEDS_HUMAN"):
        with pytest.raises(WorkflowRouteNotFound):
            resolve_route(value, "tester", result)


def test_rejects_ambiguous_or_missing_routes() -> None:
    ambiguous = graph(
        WorkflowEdgeData("one", "tester", "executor", "TEST_FAILED"),
        WorkflowEdgeData("two", "tester", "reviewer", "TEST_FAILED"),
    )
    with pytest.raises(WorkflowRouteNotFound, match="multiple routes"):
        resolve_route(ambiguous, "tester", "TEST_FAILED")
    with pytest.raises(WorkflowRouteNotFound, match="No route"):
        resolve_route(graph(), "tester", "TEST_PASS")


def test_progress_evidence_ignores_per_job_handoff_metadata() -> None:
    first = {"job_id": "one", "summary": "first wording", "data": {"failed": ["a"]}}
    second = {"job_id": "two", "summary": "other wording", "data": {"failed": ["a"]}}

    assert _stable_progress_evidence(first) == _stable_progress_evidence(second)


def test_orchestrator_relays_the_same_typed_result_to_configured_agent() -> None:
    value = WorkflowGraphData(
        1,
        (
            WorkflowNodeData("planner", "THINKER", "Planner", 0, 0),
            WorkflowNodeData("controller", "ORCHESTRATOR", "Controller", 1, 0),
            WorkflowNodeData("executor", "EXECUTOR", "Builder", 2, 0),
        ),
        (
            WorkflowEdgeData("plan", "planner", "controller", "PLAN_READY"),
            WorkflowEdgeData("dispatch", "controller", "executor", "PLAN_READY"),
        ),
    )
    decisions = resolve_handoff(value, "planner", "PLAN_READY")
    assert [item.edge.id for item in decisions] == ["plan", "dispatch"]
    assert decisions[-1].target.id == "executor"


def test_orchestrator_relay_cycle_is_rejected() -> None:
    value = WorkflowGraphData(
        1,
        (WorkflowNodeData("controller", "ORCHESTRATOR", "Controller", 0, 0),),
        (WorkflowEdgeData("loop", "controller", "controller", "always"),),
    )
    with pytest.raises(WorkflowRouteNotFound, match="cycle"):
        resolve_handoff(value, "controller", "PLAN_READY")


def test_questions_are_directed_and_do_not_change_handoff_routing() -> None:
    value = WorkflowGraphData(
        1,
        (
            WorkflowNodeData("executor", "EXECUTOR", "Builder", 0, 0),
            WorkflowNodeData("controller", "ORCHESTRATOR", "Controller", 0, 0),
            WorkflowNodeData("thinker", "THINKER", "Planner", 0, 0),
            WorkflowNodeData("reviewer", "REVIEWER", "Reviewer", 0, 0),
            WorkflowNodeData("disabled", "TESTER", "Disabled", 0, 0, enabled=False),
        ),
        (
            WorkflowEdgeData("work", "executor", "reviewer", "success"),
            WorkflowEdgeData(
                "ask",
                "executor",
                "controller",
                "consultation",
                configuration={"kind": "consultation"},
            ),
            WorkflowEdgeData(
                "relay",
                "controller",
                "thinker",
                "consultation",
                configuration={"kind": "consultation"},
            ),
            WorkflowEdgeData(
                "blocked",
                "controller",
                "disabled",
                "consultation",
                configuration={"kind": "consultation"},
            ),
        ),
    )
    assert consultation_targets(value, "executor") == {"thinker"}
    assert consultation_targets(value, "thinker") == set()
    assert resolve_route(value, "executor", "IMPLEMENTED").target.id == "reviewer"
    with pytest.raises(WorkflowRouteNotFound):
        resolve_route(value, "executor", "consultation")
