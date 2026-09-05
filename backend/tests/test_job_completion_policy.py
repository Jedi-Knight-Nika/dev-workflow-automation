import pytest

from app.domain.jobs import CompletionDirective, success_directive


@pytest.mark.parametrize(
    ("role", "action", "outcome", "data", "expected"),
    [
        (
            "INTAKE",
            "INTERPRET_TASK",
            "EVENT_INTERPRETED",
            {"actionability": "ACTION_REQUIRED"},
            CompletionDirective.INTAKE_PLAN,
        ),
        (
            "INTAKE",
            "INTERPRET_EXTERNAL_COMMENT",
            "EVENT_INTERPRETED",
            {"actionability": "INFORMATIONAL"},
            CompletionDirective.INTAKE_INFORMATIONAL,
        ),
        (
            "INTAKE",
            "INTERPRET_EXTERNAL_COMMENT",
            "EVENT_INTERPRETED",
            {"actionability": "ACTION_REQUIRED", "event_type": "REVIEW_FIX"},
            CompletionDirective.INTAKE_REPAIR,
        ),
        ("THINKER", "CREATE_PLAN", "PLAN_READY", {}, CompletionDirective.THINKER_EXECUTE),
        (
            "THINKER",
            "CREATE_PLAN",
            "NEEDS_CONTEXT",
            {},
            CompletionDirective.THINKER_NEEDS_CONTEXT,
        ),
        (
            "EXECUTOR",
            "IMPLEMENT_PLAN",
            "TEST_FAILED",
            {},
            CompletionDirective.EXECUTOR_REPAIR,
        ),
        (
            "EXECUTOR",
            "IMPLEMENT_PLAN",
            "PLAN_MISMATCH",
            {},
            CompletionDirective.EXECUTOR_REPLAN,
        ),
        ("REVIEWER", "REVIEW_CHANGES", "PASS", {}, CompletionDirective.REVIEW_PUBLISH),
        (
            "REVIEWER",
            "REVIEW_CHANGES",
            "FAIL_ACTIONABLE",
            {},
            CompletionDirective.REVIEW_REPAIR,
        ),
        (
            "REVIEWER",
            "REVIEW_CHANGES",
            "FAIL_ARCHITECTURAL",
            {},
            CompletionDirective.REVIEW_REPLAN,
        ),
    ],
)
def test_success_outcomes_map_to_domain_directives(
    role: str,
    action: str,
    outcome: str,
    data: dict[str, str],
    expected: CompletionDirective,
) -> None:
    assert success_directive(role=role, action=action, outcome=outcome, data=data) == expected


def test_repeated_reviewer_finding_overrides_repair_route() -> None:
    assert (
        success_directive(
            role="REVIEWER",
            action="REVIEW_CHANGES",
            outcome="FAIL_ACTIONABLE",
            data={},
            repeat_count=2,
            max_same_finding_repeats=2,
        )
        == CompletionDirective.REVIEW_NEEDS_HUMAN
    )


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported job role"):
        success_directive(role="UNKNOWN", action="x", outcome="x", data={})
