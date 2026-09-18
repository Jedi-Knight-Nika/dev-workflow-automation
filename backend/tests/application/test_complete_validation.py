import asyncio
from unittest.mock import AsyncMock

import pytest

from app.engineering.application.complete_validation import complete_validation
from app.engineering.application.jobs import PhaseBlocked
from app.engineering.domain.lifecycle import Action, WaitReason


@pytest.mark.parametrize(
    "passed,changes,expected",
    [
        (False, False, Action.VALIDATION_FAILED),
        (False, True, Action.VALIDATION_FAILED),
        (True, False, Action.VALIDATION_PASSED),
        (True, True, Action.VALIDATION_FAILED),
    ],
)
async def test_review_only_runs_after_passing_validation(passed, changes, expected):
    review = AsyncMock(return_value=changes)
    assert (
        await complete_validation(passed=passed, no_progress_count=0, review_changes=review)
        == expected
    )
    assert review.await_count == int(passed)


@pytest.mark.parametrize("passed", [False, True])
@pytest.mark.parametrize("count", [2, 3])
async def test_no_progress_stop_prevents_review(passed, count):
    review = AsyncMock()
    with pytest.raises(PhaseBlocked, match="Repeated validation failure") as stopped:
        await complete_validation(passed=passed, no_progress_count=count, review_changes=review)
    assert stopped.value.reason == WaitReason.MISSING_REQUIREMENT
    review.assert_not_awaited()


@pytest.mark.parametrize("error", [ValueError("stale"), asyncio.CancelledError()])
async def test_review_failure_or_cancellation_never_becomes_validation_success(error):
    review = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await complete_validation(passed=True, no_progress_count=0, review_changes=review)
    review.assert_awaited_once_with()
