import types
import uuid
from datetime import UTC, datetime
from typing import Self

import pytest

from app.application.jobs import CompleteTesterJob
from app.application.ports.tester_completion import (
    TesterCompletionCommand as CompletionCommand,
)
from app.application.ports.tester_completion import (
    TesterCompletionContext as CompletionContext,
)


class FakeTesterUnitOfWork:
    def __init__(self, context: CompletionContext | None) -> None:
        self.context = context
        self.applied = False
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

    async def begin(self, _command: CompletionCommand) -> CompletionContext | None:
        return self.context

    async def finish_during_takeover(self, _context: CompletionContext) -> None:
        self.takeover = True

    async def apply(self, _context: CompletionContext) -> None:
        self.applied = True

    async def commit(self) -> None:
        self.committed = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True


def completion_context(*, takeover: bool = False) -> CompletionContext:
    return CompletionContext(
        uuid.uuid4(), uuid.uuid4(), "TEST_PASS", {"result": "TEST_PASS"}, takeover
    )


def command() -> CompletionCommand:
    return CompletionCommand(uuid.uuid4(), uuid.uuid4(), {}, datetime.now(UTC))


@pytest.mark.asyncio
async def test_tester_completion_applies_result_and_commits() -> None:
    unit = FakeTesterUnitOfWork(completion_context())
    handler = CompleteTesterJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.applied and unit.committed and unit.synchronized


@pytest.mark.asyncio
async def test_tester_completion_preserves_manual_takeover() -> None:
    unit = FakeTesterUnitOfWork(completion_context(takeover=True))
    handler = CompleteTesterJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.takeover and unit.committed and unit.synchronized
    assert not unit.applied
