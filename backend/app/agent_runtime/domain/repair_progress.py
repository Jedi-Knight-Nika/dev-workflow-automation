"""Evidence-based continuation within an already admitted bounded work unit."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairAllowance:
    classification: str
    continue_work: bool
    effort: str
    reason: str


def repair_allowance(
    previous_failures: frozenset[str] | None,
    current_failures: frozenset[str],
    *,
    attempts: int,
    hard_attempt_limit: int = 4,
) -> RepairAllowance:
    """An edit or different error wording alone never earns another repair."""
    if not current_failures:
        return RepairAllowance("PRODUCTIVE", False, "low", "Checks passed")
    if attempts >= hard_attempt_limit:
        return RepairAllowance("STALLED", False, "low", "Work-unit attempt ceiling reached")
    if previous_failures is None:
        return RepairAllowance("MARGINAL", True, "low", "One initial repair is available")
    if current_failures < previous_failures:
        return RepairAllowance("PRODUCTIVE", True, "medium", "Deterministic failures decreased")
    if current_failures - previous_failures:
        return RepairAllowance("REGRESSING", False, "low", "Repair introduced new failing checks")
    return RepairAllowance("STALLED", False, "low", "Repair did not resolve a failing check")
