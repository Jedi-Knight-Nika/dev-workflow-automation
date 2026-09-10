from dataclasses import replace

from app.delivery.domain.review import ReviewedMessage, ReviewMessage, resolved_duplicate


def test_only_live_identical_same_actor_sha_approval_resolves_unknown():
    old = ReviewMessage("issue_comment", "1", "owner", "sha", "go merge", "2026-09-10T01:00:00Z")
    new = replace(old, source_id="2", updated_at="2026-09-10T01:01:00Z")
    unknown = ReviewedMessage(
        old.key, old.actor_id, old.head_sha, old.digest, old.updated_at, "NEEDS_CLASSIFICATION"
    )
    approval = ReviewedMessage(
        new.key, new.actor_id, new.head_sha, new.digest, new.updated_at, "APPROVAL_INTERPRETED"
    )
    assert resolved_duplicate(old, unknown, (old, new), (unknown, approval))
    for changed in (
        replace(new, body="do not merge"),
        replace(new, actor_id="other"),
        replace(new, head_sha="other"),
    ):
        assert not resolved_duplicate(old, unknown, (old, changed), (unknown, approval))
    assert not resolved_duplicate(old, unknown, (old,), (unknown, approval))
    assert not resolved_duplicate(
        old, replace(unknown, decision="FEEDBACK_PENDING"), (old, new), (approval,)
    )
