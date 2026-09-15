import pytest
from pydantic import ValidationError

from app.coordinator.domain.protocol import validate_effect
from app.coordinator.infrastructure.schemas import parse_decision


def decision(action="REPLY", **values):
    return parse_decision(
        {
            "version": 1,
            "action": action,
            "message": "Mobile support is included.",
            "engineering_request": "Implement mobile support",
            "reason": "The user clarified scope",
            "choices": [],
            "read_tools": [],
            "checkpoint": {"goal": "Mobile support", "invariants": [], "open_questions": []},
            **values,
        }
    )


@pytest.mark.parametrize(
    "values",
    [
        {"action": "MERGE"},
        {"version": 2},
        {"url": "https://example.com"},
        {"action": "ASK_HUMAN", "message": " "},
        {"action": "IMPLEMENT", "engineering_request": ""},
    ],
)
def test_invalid_authority_or_incomplete_decisions_are_rejected(values):
    with pytest.raises(ValidationError):
        decision(**values)


@pytest.mark.parametrize(
    "values",
    [
        {"current_revision": 2},
        {"current_requirement": 2},
        {"manual_takeover": True},
        {"status": "PAUSED"},
        {"status": "WAITING_HUMAN"},
        {"engineering_event": True},
    ],
)
def test_stale_or_unauthorized_work_is_rejected(values):
    kwargs = {
        "status": "ACTIVE",
        "manual_takeover": False,
        "expected_revision": 1,
        "current_revision": 1,
        "expected_requirement": 1,
        "current_requirement": 1,
    }
    with pytest.raises(ValueError):
        validate_effect(decision("REPAIR"), **(kwargs | values))
