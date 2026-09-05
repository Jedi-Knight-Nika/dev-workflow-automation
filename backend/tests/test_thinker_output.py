import pytest
from pydantic import ValidationError

from app.db.models import JobRole
from app.infrastructure.workers.structured_output import validate_role_output


def test_intake_requires_the_versioned_terminal_result() -> None:
    result = validate_role_output(
        JobRole.INTAKE,
        '{"result":"EVENT_INTERPRETED","event_type":"NEW_TASK","actionability":"ACTION_REQUIRED","blocking":false,"summary":"Implement the request","confidence":0.95}',
    )
    assert result["result"] == "EVENT_INTERPRETED"


def test_intake_rejects_unknown_actionability() -> None:
    with pytest.raises(ValidationError):
        validate_role_output(
            JobRole.INTAKE,
            '{"result":"EVENT_INTERPRETED","event_type":"NEW_TASK","actionability":"MAYBE","blocking":false,"summary":"Unknown","confidence":0.5}',
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
