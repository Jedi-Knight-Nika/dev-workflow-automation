from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.delivery.domain.merge import MergePolicy
from app.delivery.domain.review import ReviewedMessage
from app.delivery.infrastructure.github import GitHubDelivery
from app.delivery.infrastructure.review_messages import human_message
from tests.infrastructure.test_delivery import SHA, fixture_payloads

VALIDATED = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)


def comment() -> dict:
    return {
        "id": 30,
        "body": "lgtm",
        "user": {"id": 7, "type": "User"},  # PR author, deliberately not allowlisted
        "updated_at": (VALIDATED + timedelta(minutes=1)).isoformat(),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change,blocker",
    [
        ("none", None),
        ("unclassified", "REVIEW_MESSAGES_PENDING"),
        ("edited", "REVIEW_MESSAGES_PENDING"),
        ("deleted", "APPROVAL_MISSING"),
        ("bot", "APPROVAL_MISSING"),
        ("old_comment", "APPROVAL_MISSING"),
        ("stale_interpretation", "REVIEW_MESSAGES_PENDING"),
        ("failed_ci", "CHECKS_NOT_GREEN"),
        ("head_changed", "HEAD_CHANGED"),
        ("changes_requested", "BLOCKING_REVIEW"),
        ("dismissed", "APPROVAL_MISSING"),
        ("allowlist", "APPROVAL_MISSING"),
        ("formal_only", "APPROVAL_MISSING"),
        ("suspended", "TASK_SUSPENDED"),
    ],
)
async def test_natural_approval_is_bound_to_fresh_human_message_and_current_checks(
    change: str, blocker: str | None
) -> None:
    data = fixture_payloads()
    value = comment()
    message = human_message("issue_comment", value, SHA, VALIDATED)
    assert message
    reviewed = (
        ReviewedMessage(
            message.key,
            message.actor_id,
            "b" * 40 if change == "stale_interpretation" else SHA,
            message.digest,
            message.updated_at,
            "APPROVAL_INTERPRETED",
        ),
    )
    reviews = []
    if change == "unclassified":
        reviewed = ()
    elif change == "edited":
        value["body"] = "Do not merge, I found a bug"
    elif change == "bot":
        value["user"]["type"] = "Bot"
    elif change == "old_comment":
        value["updated_at"] = (VALIDATED - timedelta(seconds=1)).isoformat()
    elif change == "failed_ci":
        data[f"/repos/acme/repo/commits/{SHA}/check-runs"]["check_runs"][0]["conclusion"] = (
            "failure"
        )
    elif change in {"changes_requested", "dismissed"}:
        reviews = [{"id": 40, "state": change.upper(), "commit_id": SHA, "user": value["user"]}]
    data["/repos/acme/repo/pulls/1/reviews"] = reviews
    data["/repos/acme/repo/issues/1/comments"] = [] if change == "deleted" else [value]
    data["/repos/acme/repo/pulls/1/comments"] = []
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=data[request.url.path])
        ),
    ) as client:
        policy = MergePolicy(
            True, True, frozenset(), change == "formal_only", change != "allowlist"
        )
        evidence, _ = await GitHubDelivery(client, "acme", "repo").evidence(
            1,
            "b" * 40 if change == "head_changed" else SHA,
            SHA,
            policy,
            ("test",),
            runnable=change != "suspended",
            reviewed_messages=reviewed,
            validated_at=VALIDATED,
        )
    if blocker is None:
        assert policy.blockers(evidence) == ()
        assert evidence.approval and evidence.approval.actor_id == "7"
    else:
        assert blocker in policy.blockers(evidence)


@pytest.mark.parametrize("source", ["issue_comment", "review_comment", "review"])
def test_message_snapshot_rejects_stale_revision_or_invalid_date(source: str) -> None:
    value = comment()
    assert human_message(source, value, SHA, VALIDATED)
    value["commit_id"] = "b" * 40
    assert human_message(source, value, SHA, VALIDATED) is None
    value["commit_id"] = SHA
    for timestamp in ["", "invalid", "2026-09-08T10:00:00"]:
        value["updated_at"] = timestamp
        assert human_message(source, value, SHA, VALIDATED) is None
