import json

import pytest

from app.engineering.domain.validation import CheckResult, ValidationResult


@pytest.mark.parametrize(
    "exit_code,timed_out,passed",
    [(0, False, True), (1, False, False), (None, False, False), (0, True, False)],
)
def test_check_requires_successful_exit_without_timeout(exit_code, timed_out, passed):
    assert CheckResult(("check",), exit_code, "", timed_out).passed is passed


@pytest.mark.parametrize(
    "passed,previous,count,expected",
    [
        (False, "same", 0, 1),
        (False, "same", 1, 2),
        (False, "same", 2, 3),
        (False, "different", 2, 0),
        (False, None, 2, 0),
        (True, "same", 2, 0),
    ],
)
def test_progress_only_accumulates_unchanged_failures(passed, previous, count, expected):
    result = ValidationResult(passed, "head", "same", ())
    assert result.progress_count(previous, count) == expected


def test_feedback_preserves_failure_order_and_bounded_output():
    result = ValidationResult(
        False,
        "head",
        "fingerprint",
        (
            CheckResult(("pass",), 0, "Exclude this"),
            CheckResult(("fail", "--strict"), 1, "x" * 1200 + "tail"),
            CheckResult(("timeout",), 0, "Timed out", True),
            CheckResult(("killed",), None, "Interrupted"),
        ),
    )
    prefix, payload = result.repair_feedback().split("\n", 1)
    assert prefix == (
        "Fix these deterministic validation failures. Full logs remain in validation evidence:"
    )
    failures = json.loads(payload)
    assert [check["command"] for check in failures] == [
        ["fail", "--strict"],
        ["timeout"],
        ["killed"],
    ]
    assert failures[0]["output_tail"] == "x" * 996 + "tail"
    assert failures[1]["exit_code"] == 0 and failures[1]["timed_out"] is True
    assert failures[2]["exit_code"] is None


def test_feedback_retains_existing_batch_length_limit():
    checks = tuple(CheckResult(("check",), 1, "x" * 2000) for _ in range(12))
    feedback = ValidationResult(False, "head", "fingerprint", checks).repair_feedback()
    expected = json.dumps(
        [
            {"command": ["check"], "exit_code": 1, "timed_out": False, "output_tail": "x" * 1000}
            for _ in checks
        ]
    )[:8000]
    assert feedback.split("\n", 1)[1] == expected


def test_passing_checks_do_not_override_failed_batch_result():
    result = ValidationResult(False, "head", "same", (CheckResult(("check",), 0, ""),))
    assert result.progress_count("same", 1) == 2
    assert result.repair_feedback().endswith("\n[]")
