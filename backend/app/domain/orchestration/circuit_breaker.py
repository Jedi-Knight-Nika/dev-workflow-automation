from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    next_probe_at: datetime | None = None


def record_failure(
    snapshot: CircuitSnapshot,
    *,
    now: datetime,
    failure_threshold: int = 3,
    cooldown_seconds: int = 60,
) -> CircuitSnapshot:
    failures = snapshot.consecutive_failures + 1
    if snapshot.state is CircuitState.HALF_OPEN or failures >= failure_threshold:
        return CircuitSnapshot(
            CircuitState.OPEN, failures, now + timedelta(seconds=cooldown_seconds)
        )
    return CircuitSnapshot(CircuitState.CLOSED, failures, None)


def allow_probe(snapshot: CircuitSnapshot, *, now: datetime) -> CircuitSnapshot:
    if (
        snapshot.state is CircuitState.OPEN
        and snapshot.next_probe_at is not None
        and snapshot.next_probe_at <= now
    ):
        return CircuitSnapshot(CircuitState.HALF_OPEN, snapshot.consecutive_failures, None)
    return snapshot


def record_success(snapshot: CircuitSnapshot) -> CircuitSnapshot:
    return CircuitSnapshot()
