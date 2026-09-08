from decimal import Decimal

from app.engineering.application.task_usage import UsageSample, task_usage


def test_task_usage_combines_history_and_native_turns_without_losing_missing_cost() -> None:
    result = task_usage(
        [
            UsageSample("EXECUTOR", "openai", "legacy", 100, 20, 1000, Decimal("0.1")),
            UsageSample("DEVELOPER", "openai", "native", 50, 10, 500, Decimal("0.02"), native=True),
        ]
    )
    assert result.input_tokens == 150 and result.output_tokens == 30
    assert result.attempts == 2 and result.native_turns == 1
    assert result.estimated_cost_usd == 0.12 and result.duration_ms == 1500
    assert {r.role for r in result.roles} == {"EXECUTOR", "DEVELOPER"}


def test_partial_native_receipt_is_not_a_free_turn() -> None:
    result = task_usage(
        [
            UsageSample(
                "DEVELOPER", "openai", "native", 50, None, None, None, native=True, complete=False
            )
        ]
    )
    assert result.estimated_cost_usd is None and result.missing_usage_attempts == 1
    assert result.native_turns == 1


def test_reported_zero_is_not_treated_as_unknown() -> None:
    result = task_usage(
        [UsageSample("DEVELOPER", "anthropic", "native", 0, 0, 0, Decimal(0), native=True)]
    )
    assert result.estimated_cost_usd == 0
    assert result.missing_usage_attempts == 0
