from app.intake.infrastructure.github_events import pull_request_number, validation_from_event


def test_issue_comment_uses_nested_pull_request_number() -> None:
    assert pull_request_number({"issue": {"number": 39, "pull_request": {}}}) == 39


def test_check_run_is_bound_to_its_head_sha() -> None:
    result = validation_from_event(
        "check_run",
        {
            "check_run": {
                "name": "Quality gate",
                "status": "completed",
                "conclusion": "success",
                "head_sha": "abc123",
                "html_url": "https://example.test/check/1",
            }
        },
    )

    assert result == (
        "CHECK",
        "Quality gate",
        "SUCCESS",
        "abc123",
        "https://example.test/check/1",
    )


def test_review_uses_reviewed_commit_not_current_head() -> None:
    result = validation_from_event(
        "pull_request_review",
        {
            "action": "submitted",
            "review": {
                "state": "changes_requested",
                "commit_id": "old-sha",
                "user": {"login": "reviewer"},
            },
            "pull_request": {"head": {"sha": "new-sha"}},
        },
    )

    assert result is not None
    assert result[2] == "CHANGES_REQUESTED"
    assert result[3] == "old-sha"


def test_inline_review_comment_becomes_sha_aware_actionable_evidence() -> None:
    result = validation_from_event(
        "pull_request_review_comment",
        {
            "action": "created",
            "comment": {
                "commit_id": "comment-sha",
                "html_url": "https://example.test/comment/1",
                "user": {"login": "review-bot"},
            },
        },
    )

    assert result == (
        "REVIEW_COMMENT",
        "review-bot",
        "ACTION_REQUIRED",
        "comment-sha",
        "https://example.test/comment/1",
    )


def test_pending_check_suite_is_preserved_as_pending_evidence() -> None:
    result = validation_from_event(
        "check_suite",
        {
            "check_suite": {
                "status": "in_progress",
                "head_sha": "current-sha",
                "app": {"name": "GitHub Actions"},
            }
        },
    )

    assert result is not None
    assert result[:4] == ("CHECK_SUITE", "GitHub Actions", "IN_PROGRESS", "current-sha")
