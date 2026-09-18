from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.activity.domain.events import amount, file_path, task_activity


def test_projection_copies_only_known_public_facts():
    event = task_activity(
        1,
        uuid4(),
        "TASK_LIFECYCLE_CHANGED",
        {
            "to_status": "ACTIVE",
            "to_stage": "DEVELOPING",
            "version": 2,
            "action": "private_token",
            "run_id": str(uuid4()),
            "prompt": "secret prompt",
            "body": "private message",
            "error": "https://user:password@example.test",
            "from_stage": "secret",
        },
        datetime.now(UTC),
        "engineering",
    )
    assert event.kind == "TASK_STATE_CHANGED"
    assert set(event.payload) == {"to_status", "to_stage", "version", "run_id"}
    assert event.payload["to_status"] == "ACTIVE"


@pytest.mark.parametrize(
    "path", ["../secret", "/etc/passwd", "x/../../secret", "a\nb", "a|b", "a\\b"]
)
def test_unsafe_file_paths_are_not_exportable(path):
    assert file_path(path) is None


def test_unknown_billing_is_distinct_from_zero_and_nonfinite_values():
    assert amount("0") == "0"
    assert amount(None) is None
    assert amount("NaN") is None
    assert amount("Infinity") is None
    assert amount("-1") is None


def test_actor_and_coordinator_action_use_existing_domain_facts():
    event = task_activity(
        1, uuid4(), "COORDINATOR_DECIDED", {"action": "REPLY"}, datetime.now(UTC), "coordinator"
    )
    assert event.payload["action"] == "REPLY"
    assert event.actor == "Coordinator"
    paused = task_activity(
        2,
        uuid4(),
        "TASK_LIFECYCLE_CHANGED",
        {"actor": "user:ticket-control", "action": "PAUSE"},
        datetime.now(UTC),
        "engineering",
    )
    assert paused.actor_type == "human"
    assert "actor" not in paused.payload
