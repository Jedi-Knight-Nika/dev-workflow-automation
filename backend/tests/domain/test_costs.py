from decimal import Decimal

import pytest

from app.agent_runtime.domain.usage import Pricing, Usage, budget_blocker
from app.agent_runtime.infrastructure.normalization import claude_usage, codex_usage


def test_cached_tokens_and_reasoning_are_not_double_counted() -> None:
    usage = Usage(1000, 100, 800, 100, 50)
    prices = Pricing(Decimal(2), Decimal(12), Decimal("0.2"), Decimal("2.5"))
    assert prices.calculate(usage) == Decimal("0.00181")


def test_unknown_usage_and_unknown_cache_price_are_not_zero_cost() -> None:
    prices = Pricing(Decimal(2), Decimal(12))
    assert prices.calculate(Usage()) is None
    assert prices.calculate(Usage(100, 20, 50, 0)) is None
    assert prices.calculate(Usage(100, 20, 0, 0)) == Decimal("0.00044")


@pytest.mark.parametrize(
    "amount,expected",
    [(None, "USAGE_INCOMPLETE"), (Decimal(5), "BUDGET_EXHAUSTED"), (Decimal(1), None)],
)
def test_budget_uses_money_not_total_cached_tokens(
    amount: Decimal | None, expected: str | None
) -> None:
    assert budget_blocker(hard_limit=Decimal(5), consumed=amount) == expected


@pytest.mark.parametrize(
    "usage",
    [
        {"input_tokens": -1},
        {"input_tokens": True},
        {"input_tokens": 1, "cache_read_input_tokens": 2},
        {"provider_cost_usd": Decimal("NaN")},
    ],
)
def test_invalid_usage_rejected(usage: dict) -> None:
    with pytest.raises(ValueError):
        Usage(**usage)


def test_codex_counts_whole_turn_delta_not_last_request_or_whole_session() -> None:
    before = {
        "input_tokens": 1000,
        "output_tokens": 100,
        "cached_input_tokens": 800,
        "cache_write_input_tokens": 0,
        "reasoning_output_tokens": 50,
    }
    after = {
        "input_tokens": 1500,
        "output_tokens": 160,
        "cached_input_tokens": 1200,
        "cache_write_input_tokens": 0,
        "reasoning_output_tokens": 70,
    }
    assert codex_usage(after, before) == Usage(500, 60, 400, 0, 20)
    assert not codex_usage(after, None).complete
    assert codex_usage(before, after).input_tokens is None


def test_claude_normalizes_input_convention_and_preserves_provider_cost() -> None:
    usage = claude_usage(
        {
            "input_tokens": 100,
            "output_tokens": 10,
            "cache_read_input_tokens": 800,
            "cache_creation_input_tokens": 100,
        },
        0.003,
    )
    assert usage == Usage(1000, 10, 800, 100, provider_cost_usd=Decimal("0.003"))
    assert not claude_usage({"input_tokens": 100}, None).complete
