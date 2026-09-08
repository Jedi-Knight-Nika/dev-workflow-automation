from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.application.ports.task_history import TaskMetricsView, TaskRoleMetricsView


@dataclass(frozen=True)
class UsageSample:
    role: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    cost_usd: Decimal | None
    native: bool = False
    complete: bool = True


def task_usage(samples: Sequence[UsageSample]) -> TaskMetricsView:
    buckets: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    cost: Decimal | None = Decimal(0) if samples else None
    missing = 0
    for sample in samples:
        if not sample.complete or sample.input_tokens is None or sample.output_tokens is None:
            missing += 1
        if sample.cost_usd is None:
            cost = None
        elif cost is not None:
            cost += sample.cost_usd
        bucket = buckets[(sample.role, sample.provider, sample.model)]
        for i, value in enumerate(
            (1, sample.input_tokens or 0, sample.output_tokens or 0, sample.duration_ms or 0)
        ):
            bucket[i] += value
    roles = tuple(
        TaskRoleMetricsView(role, provider, model, *values)
        for (role, provider, model), values in buckets.items()
    )
    return TaskMetricsView(
        attempts=len(samples),
        input_tokens=sum(r.input_tokens for r in roles),
        output_tokens=sum(r.output_tokens for r in roles),
        duration_ms=sum(r.duration_ms for r in roles),
        missing_usage_attempts=missing,
        estimated_cost_usd=float(cost) if cost is not None else None,
        roles=roles,
        native_turns=sum(s.native for s in samples),
    )
