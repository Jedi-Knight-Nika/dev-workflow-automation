import pytest
from pydantic import ValidationError

from app.db.models import JobRole
from app.infrastructure.workers.structured_output import validate_role_output


def test_intake_requires_the_versioned_terminal_result() -> None:
    result = validate_role_output(
        JobRole.INTAKE,
        '{"result":"EVENT_INTERPRETED","event_type":"NEW_TASK","actionability":"ACTION_REQUIRED","blocking":false,"summary":"Implement the request","confidence":0.95,"external_delivery_actions":[]}',
    )
    assert result["result"] == "EVENT_INTERPRETED"


def test_intake_rejects_unknown_actionability() -> None:
    with pytest.raises(ValidationError):
        validate_role_output(
            JobRole.INTAKE,
            '{"result":"EVENT_INTERPRETED","event_type":"NEW_TASK","actionability":"MAYBE","blocking":false,"summary":"Unknown","confidence":0.5}',
        )


def test_intake_accepts_typed_github_delivery_actions() -> None:
    result = validate_role_output(
        JobRole.INTAKE,
        '{"result":"EVENT_INTERPRETED","event_type":"INFORMATIONAL",'
        '"actionability":"INFORMATIONAL","blocking":false,"summary":"Rename and merge",'
        '"confidence":1,"external_delivery_actions":['
        '{"action":"UPDATE_PR_TITLE","value":"feat: improve shell translucency"},'
        '{"action":"MERGE_PULL_REQUEST"}]}',
    )

    assert result["external_delivery_actions"] == [
        {"action": "UPDATE_PR_TITLE", "value": "feat: improve shell translucency"},
        {"action": "MERGE_PULL_REQUEST", "value": None},
    ]


def test_intake_accepts_commit_message_update_action() -> None:
    result = validate_role_output(
        JobRole.INTAKE,
        '{"result":"EVENT_INTERPRETED","event_type":"INFORMATIONAL",'
        '"actionability":"INFORMATIONAL","blocking":false,"summary":"Rename commit",'
        '"confidence":1,"external_delivery_actions":['
        '{"action":"UPDATE_COMMIT_MESSAGE","value":"feat: improve shell translucency"}]}',
    )

    assert result["external_delivery_actions"][0]["action"] == "UPDATE_COMMIT_MESSAGE"


def test_intake_rejects_merge_action_with_an_arbitrary_value() -> None:
    with pytest.raises(ValidationError, match="does not accept a value"):
        validate_role_output(
            JobRole.INTAKE,
            '{"result":"EVENT_INTERPRETED","event_type":"INFORMATIONAL",'
            '"actionability":"INFORMATIONAL","blocking":false,"summary":"Merge",'
            '"confidence":1,"external_delivery_actions":['
            '{"action":"MERGE_PULL_REQUEST","value":"force"}]}',
        )


def test_thinker_accepts_plan_ready() -> None:
    result = validate_role_output(
        JobRole.THINKER,
        '{"result":"PLAN_READY","goal":"Ship it","targets":[],"ordered_steps":["Edit"],"constraints":[],"required_tests":[],"risks":[],"acceptance_criteria":["Passes"]}',
    )
    assert result["result"] == "PLAN_READY"


def test_thinker_requires_questions_when_context_is_missing() -> None:
    with pytest.raises(ValidationError, match="at least one question"):
        validate_role_output(
            JobRole.THINKER,
            '{"result":"NEEDS_CONTEXT","reason":"Requirement is ambiguous"}',
        )


def test_thinker_accepts_human_escalation() -> None:
    result = validate_role_output(
        JobRole.THINKER,
        '{"result":"NEEDS_HUMAN","reason":"Conflicting business invariants"}',
    )
    assert result["reason"] == "Conflicting business invariants"


def test_tester_accepts_passing_validation() -> None:
    result = validate_role_output(
        JobRole.TESTER,
        '{"result":"TEST_PASS","summary":"All validation passed","findings":[]}',
    )
    assert result["result"] == "TEST_PASS"


def test_tester_failure_requires_a_concrete_finding() -> None:
    with pytest.raises(ValidationError, match="concrete findings"):
        validate_role_output(
            JobRole.TESTER,
            '{"result":"TEST_FAILED","summary":"Validation failed","findings":[]}',
        )
