from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Usage:
    """Input includes cache reads/writes; reasoning is a subset of output.

    Adapters normalize provider conventions before constructing this object.
    None means unavailable, not zero. Partial information must remain partial.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    provider_cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        counts = (
            self.input_tokens,
            self.output_tokens,
            self.cache_read_input_tokens,
            self.cache_write_input_tokens,
            self.reasoning_tokens,
        )
        if any(value is not None and (type(value) is not int or value < 0) for value in counts):
            raise ValueError("Token counts must be non-negative integers or unknown")
        if self.provider_cost_usd is not None and (
            not self.provider_cost_usd.is_finite() or self.provider_cost_usd < 0
        ):
            raise ValueError("Provider cost must be finite and non-negative")
        if (
            self.input_tokens is not None
            and (self.cache_read_input_tokens or 0) + (self.cache_write_input_tokens or 0)
            > self.input_tokens
        ):
            raise ValueError("Cached input cannot exceed total normalized input")
        if self.output_tokens is not None and (self.reasoning_tokens or 0) > self.output_tokens:
            raise ValueError("Reasoning tokens cannot exceed normalized output")

    @property
    def complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.input_tokens,
                self.output_tokens,
                self.cache_read_input_tokens,
                self.cache_write_input_tokens,
            )
        )


@dataclass(frozen=True)
class Pricing:
    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal | None = None
    cache_write_per_million: Decimal | None = None

    def __post_init__(self) -> None:
        for price in (
            self.input_per_million,
            self.output_per_million,
            self.cached_input_per_million,
            self.cache_write_per_million,
        ):
            if price is not None and (not price.is_finite() or price < 0):
                raise ValueError("Prices must be finite non-negative amounts")

    def calculate(self, usage: Usage) -> Decimal | None:
        if not usage.complete:
            return None
        reads, writes = usage.cache_read_input_tokens or 0, usage.cache_write_input_tokens or 0
        if reads and self.cached_input_per_million is None:
            return None
        if writes and self.cache_write_per_million is None:
            return None
        uncached = (usage.input_tokens or 0) - reads - writes
        amount = (
            uncached * self.input_per_million
            + reads * (self.cached_input_per_million or Decimal(0))
            + writes * (self.cache_write_per_million or Decimal(0))
            + (usage.output_tokens or 0) * self.output_per_million
        )
        return amount / Decimal(1_000_000)


def budget_blocker(
    *, hard_limit: Decimal, consumed: Decimal | None, reserved: Decimal = Decimal(0)
) -> str | None:
    if not hard_limit.is_finite() or hard_limit <= 0 or not reserved.is_finite() or reserved < 0:
        raise ValueError("Invalid cost budget")
    if consumed is None:
        return "USAGE_INCOMPLETE"
    if not consumed.is_finite() or consumed < 0:
        raise ValueError("Invalid consumed amount")
    return "BUDGET_EXHAUSTED" if consumed + reserved >= hard_limit else None
