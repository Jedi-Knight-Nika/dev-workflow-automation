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


@pytest.mark.parametrize(
    "kind,source,lifecycle_actor,expected",
    [
        ("TASK_CREATED", "engineering", None, ("system", "Engineering")),
        ("TASK_CREATED", "api", None, ("human", "Human")),
        ("TASK_CREATED", "user", None, ("human", "Human")),
        ("TASK_CREATED", "dashboard", None, ("human", "Human")),
        ("TASK_LIFECYCLE_CHANGED", "engineering", "user:control", ("human", "Human")),
        ("TASK_STATE_CHANGED", "engineering", "user:control", ("human", "Human")),
        ("TASK_LIFECYCLE_CHANGED", "github", "user:control", ("integration", "Github")),
        ("TASK_LIFECYCLE_CHANGED", "linear", "coordinator", ("agent", "Coordinator")),
        ("TASK_LIFECYCLE_CHANGED", "user", "coordinator", ("agent", "Coordinator")),
        ("TASK_CREATED", "engineering", "coordinator", ("system", "Engineering")),
        ("TASK_CREATED", "engineering", "user:control", ("system", "Engineering")),
        ("TASK_CREATED", "trello", None, ("integration", "Trello")),
        ("TASK_CREATED", "slack", None, ("integration", "Slack")),
        ("COORDINATOR_DECIDED", "github", None, ("agent", "Coordinator")),
        ("COORDINATOR_DECIDED", "user", "user:control", ("agent", "Coordinator")),
        ("WORK_PLAN_UPDATED", "github", "coordinator", ("agent", "Developer")),
        ("WORK_PLAN_UPDATED", "user", "user:control", ("agent", "Developer")),
    ],
)
def test_actor_precedence_does_not_expose_or_trust_unrelated_payload_actors(
    kind, source, lifecycle_actor, expected
):
    event = task_activity(1, uuid4(), kind, {"actor": lifecycle_actor}, datetime.now(UTC), source)
    assert (event.actor_type, event.actor) == expected
    assert "actor" not in event.payload


@pytest.mark.parametrize(
    "source_kind,public_kind",
    [
        ("TASK_LIFECYCLE_CHANGED", "TASK_STATE_CHANGED"),
        ("ENGINEERING_MERGE_CONFIRMED", "MERGE_COMPLETED"),
        ("HUMAN_INPUT_REQUIRED", "HUMAN_REQUIRED"),
        ("HUMAN_INPUT_RESOLVED", "HUMAN_RESPONDED"),
        ("UNKNOWN_EVENT", "UNKNOWN_EVENT"),
    ],
)
def test_event_aliases_preserve_detail_levels(source_kind, public_kind):
    event = task_activity(1, uuid4(), source_kind, {}, datetime.now(UTC), "engineering")
    assert event.kind == public_kind
    assert event.detail_level == (2 if source_kind == "UNKNOWN_EVENT" else 1)


@pytest.mark.parametrize("passed", [True, False, 1, "true", None])
def test_validation_activity_requires_explicit_boolean_success(passed):
    event = task_activity(
        1,
        uuid4(),
        "VALIDATION_BATCH_COMPLETED",
        {"passed": passed},
        datetime.now(UTC),
        "engineering",
    )
    assert event.kind == ("VALIDATION_PASSED" if passed is True else "VALIDATION_FAILED")
