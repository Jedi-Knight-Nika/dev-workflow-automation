from app.services.github_events import (
    conversational_comment,
    extract_ci_diagnostics,
    focused_validation_payload,
    validation_from_event,
)


def test_general_pr_comment_is_extracted_for_intake() -> None:
    result = conversational_comment(
        "issue_comment",
        {
            "action": "created",
            "issue": {"pull_request": {"url": "https://api.example/pr/1"}},
            "comment": {
                "body": "Do not add caching yet; another service owns it.",
                "html_url": "https://example.test/comment/2",
                "user": {"login": "reviewer"},
            },
        },
    )
    assert result is not None
    assert result["raw_text"].startswith("Do not add caching")
    assert result["author"] == "reviewer"


def test_approval_is_not_sent_to_intake() -> None:
    assert (
        conversational_comment(
            "pull_request_review",
            {"action": "submitted", "review": {"state": "approved", "body": "Looks good"}},
        )
        is None
    )


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


def test_ci_diagnostics_extract_relevant_output_and_annotations() -> None:
    result = extract_ci_diagnostics(
        "check_run",
        {
            "check_run": {
                "name": "tests",
                "conclusion": "failure",
                "details_url": "https://example.test/run/1",
                "output": {
                    "title": "Two tests failed",
                    "summary": "pytest reported assertion failures",
                    "text": "FAILED tests/test_api.py::test_create - assert 500 == 201",
                    "annotations": [
                        {
                            "path": "tests/test_api.py",
                            "start_line": 42,
                            "end_line": 42,
                            "annotation_level": "failure",
                            "message": "Expected 201 but received 500",
                        }
                    ],
                },
            }
        },
    )

    assert result["details_url"] == "https://example.test/run/1"
    assert "assert 500 == 201" in result["excerpt"]
    assert result["annotations"][0]["path"] == "tests/test_api.py"


def test_ci_diagnostics_are_bounded_before_worker_context() -> None:
    result = focused_validation_payload(
        "check_run",
        {"check_run": {"output": {"text": "x" * 50_000}}},
    )

    excerpt = result["ci_diagnostics"]["excerpt"]
    assert len(excerpt) <= 12_000
    assert excerpt.endswith("[TRUNCATED]")


def test_review_comment_payload_excludes_unrelated_webhook_data() -> None:
    result = focused_validation_payload(
        "pull_request_review_comment",
        {
            "comment": {"body": "Fix the null handling", "path": "api.py", "line": 8},
            "repository": {"sensitive_unrelated_data": "not worker context"},
        },
    )

    assert result == {
        "review_comment": {
            "body": "Fix the null handling",
            "path": "api.py",
            "line": 8,
            "url": None,
        }
    }
