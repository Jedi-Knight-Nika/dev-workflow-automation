import types
import uuid
from datetime import UTC, datetime
from typing import Self

import pytest

from app.application.jobs import CompleteReviewerJob
from app.application.ports.reviewer_completion import (
    ReviewerCompletionCommand,
    ReviewerCompletionContext,
)
from app.domain.jobs import CompletionDirective


class FakeReviewerUnitOfWork:
    def __init__(self, context: ReviewerCompletionContext | None, *, publish: bool = False) -> None:
        self.context = context
        self.publish_requested = publish
        self.directive: CompletionDirective | None = None
        self.takeover = self.committed = self.published = self.synchronized = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        return None

    async def begin(self, _command: ReviewerCompletionCommand) -> ReviewerCompletionContext | None:
        return self.context

    async def finish_during_takeover(self, _context: ReviewerCompletionContext) -> None:
        self.takeover = True

    async def apply(
        self, _context: ReviewerCompletionContext, directive: CompletionDirective
    ) -> bool:
        self.directive = directive
        return self.publish_requested

    async def commit(self) -> None:
        self.committed = True

    async def publish(self, _task_id: uuid.UUID) -> None:
        self.published = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True


def reviewer_context(
    *, outcome: str = "PASS", repeats: int = 0, takeover: bool = False
) -> ReviewerCompletionContext:
    return ReviewerCompletionContext(
        uuid.uuid4(), uuid.uuid4(), "REVIEW_CHANGES", outcome, {}, {}, repeats, takeover
    )


def command() -> ReviewerCompletionCommand:
    return ReviewerCompletionCommand(uuid.uuid4(), uuid.uuid4(), {}, datetime.now(UTC))


@pytest.mark.asyncio
async def test_reviewer_completion_commits_before_publication() -> None:
    unit = FakeReviewerUnitOfWork(reviewer_context(), publish=True)
    handler = CompleteReviewerJob(lambda: unit, 2)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.directive == CompletionDirective.REVIEW_PUBLISH
    assert unit.committed and unit.published and not unit.synchronized


@pytest.mark.asyncio
async def test_reviewer_completion_applies_repeated_finding_limit() -> None:
    unit = FakeReviewerUnitOfWork(reviewer_context(outcome="FAIL_ACTIONABLE", repeats=2))
    handler = CompleteReviewerJob(lambda: unit, 2)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.directive == CompletionDirective.REVIEW_NEEDS_HUMAN
    assert unit.committed and unit.synchronized


@pytest.mark.asyncio
async def test_reviewer_completion_preserves_manual_takeover() -> None:
    unit = FakeReviewerUnitOfWork(reviewer_context(takeover=True))
    handler = CompleteReviewerJob(lambda: unit, 2)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.takeover and unit.committed and unit.synchronized
    assert unit.directive is None
