from decimal import Decimal
from typing import Any

from app.agent_runtime.domain.usage import Usage


def token(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def codex_usage(total: dict[str, Any], previous: dict[str, Any] | None) -> Usage:
    """Native totals include every model request in the turn; `last` does not.

    A missing baseline after resume is unknown, never charged as a fresh run.
    A regressed counter is unknown rather than a negative bill.
    """

    def delta(key: str) -> int | None:
        current = token(total.get(key))
        before = token(previous.get(key)) if previous is not None else None
        if current is None or before is None or current < before:
            return None
        return current - before

    return Usage(
        input_tokens=delta("input_tokens"),
        output_tokens=delta("output_tokens"),
        cache_read_input_tokens=delta("cached_input_tokens"),
        cache_write_input_tokens=delta("cache_write_input_tokens"),
        reasoning_tokens=delta("reasoning_output_tokens"),
    )


def claude_usage(raw: dict[str, Any], cost: float | None) -> Usage:
    # Anthropic input excludes cache read/write, unlike our normalized total.
    uncached = token(raw.get("input_tokens"))
    read = token(raw.get("cache_read_input_tokens"))
    write = token(raw.get("cache_creation_input_tokens"))
    total = (
        uncached + read + write
        if uncached is not None and read is not None and write is not None
        else None
    )
    return Usage(
        input_tokens=total,
        output_tokens=token(raw.get("output_tokens")),
        cache_read_input_tokens=read,
        cache_write_input_tokens=write,
        provider_cost_usd=Decimal(str(cost)) if cost is not None else None,
    )
