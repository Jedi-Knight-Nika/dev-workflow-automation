from collections.abc import Awaitable, Callable

from app.engineering.application.jobs import PhaseBlocked
from app.engineering.domain.lifecycle import Action, WaitReason


async def complete_validation(
    *, passed: bool, no_progress_count: int, review_changes: Callable[[], Awaitable[bool]]
) -> Action:
    """Choose the next action after validation evidence has been committed."""
    if no_progress_count >= 2:
        raise PhaseBlocked(
            WaitReason.MISSING_REQUIREMENT,
            "Repeated validation failure without workspace progress; inspect before another paid turn",
        )
    if not passed or await review_changes():
        return Action.VALIDATION_FAILED
    return Action.VALIDATION_PASSED
