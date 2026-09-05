from dataclasses import dataclass


class MergeGateRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    kind: str
    name: str
    status: str


BLOCKING_STATUSES = frozenset(
    {
        "FAILURE",
        "FAILED",
        "ERROR",
        "CANCELLED",
        "TIMED_OUT",
        "ACTION_REQUIRED",
        "CHANGES_REQUESTED",
        "PENDING",
        "QUEUED",
        "IN_PROGRESS",
    }
)
CHECK_KINDS = frozenset({"CHECK", "CHECK_SUITE", "STATUS"})


def assert_merge_gates(evidence: list[ValidationEvidence]) -> None:
    latest: dict[tuple[str, str], ValidationEvidence] = {}
    for item in evidence:
        latest[(item.kind, item.name)] = item
    if not any(item.kind in CHECK_KINDS for item in latest.values()):
        raise MergeGateRejected("Latest revision has no completed CI checks")
    blocking = [item for item in latest.values() if item.status.upper() in BLOCKING_STATUSES]
    if blocking:
        raise MergeGateRejected("Latest revision has incomplete or failing gates")
