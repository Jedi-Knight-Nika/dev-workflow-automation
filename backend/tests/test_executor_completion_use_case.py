import types
import uuid
from datetime import UTC, datetime
from typing import Self

import pytest

from app.application.jobs import CompleteExecutorJob
from app.application.ports.executor_completion import (
    ExecutorCompletionCommand,
    ExecutorCompletionContext,
)
from app.domain.jobs import CompletionDirective


class FakeExecutorUnitOfWork:
    def __init__(self, context: ExecutorCompletionContext | None) -> None:
        self.context = context
        self.directive: CompletionDirective | None = None
        self.takeover = False
        self.committed = False
        self.synchronized = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        return None

    async def begin(self, _command: ExecutorCompletionCommand) -> ExecutorCompletionContext | None:
        return self.context

    async def finish_during_takeover(self, _context: ExecutorCompletionContext) -> None:
        self.takeover = True

    async def apply(
        self, _context: ExecutorCompletionContext, directive: CompletionDirective
    ) -> None:
        self.directive = directive

    async def commit(self) -> None:
        self.committed = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True


def executor_context(*, takeover: bool = False) -> ExecutorCompletionContext:
    return ExecutorCompletionContext(
        uuid.uuid4(), uuid.uuid4(), "IMPLEMENT_PLAN", "IMPLEMENTED", {}, {}, takeover
    )


def command() -> ExecutorCompletionCommand:
    return ExecutorCompletionCommand(uuid.uuid4(), uuid.uuid4(), {}, datetime.now(UTC))


@pytest.mark.asyncio
async def test_executor_completion_applies_domain_directive_and_commits() -> None:
    unit = FakeExecutorUnitOfWork(executor_context())
    handler = CompleteExecutorJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.directive == CompletionDirective.EXECUTOR_REVIEW
    assert unit.committed and unit.synchronized


@pytest.mark.asyncio
async def test_executor_completion_preserves_manual_takeover() -> None:
    unit = FakeExecutorUnitOfWork(executor_context(takeover=True))
    handler = CompleteExecutorJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.takeover and unit.committed and unit.synchronized
    assert unit.directive is None
