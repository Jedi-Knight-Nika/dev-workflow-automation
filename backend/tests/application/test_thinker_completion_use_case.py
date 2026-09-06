import types
import uuid
from datetime import UTC, datetime
from typing import Self

import pytest

from app.application.jobs import CompleteThinkerJob
from app.application.ports.thinker_completion import (
    ThinkerCompletionCommand,
    ThinkerCompletionContext,
)
from app.domain.jobs import CompletionDirective


class FakeThinkerUnitOfWork:
    def __init__(self, context: ThinkerCompletionContext | None) -> None:
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

    async def begin(self, _command: ThinkerCompletionCommand) -> ThinkerCompletionContext | None:
        return self.context

    async def finish_during_takeover(self, _context: ThinkerCompletionContext) -> None:
        self.takeover = True

    async def apply(
        self, _context: ThinkerCompletionContext, directive: CompletionDirective
    ) -> None:
        self.directive = directive

    async def commit(self) -> None:
        self.committed = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True


def thinker_context(*, takeover: bool = False) -> ThinkerCompletionContext:
    return ThinkerCompletionContext(
        uuid.uuid4(),
        uuid.uuid4(),
        "PLAN_READY",
        {},
        takeover,
    )


def command() -> ThinkerCompletionCommand:
    return ThinkerCompletionCommand(uuid.uuid4(), uuid.uuid4(), {}, datetime.now(UTC))


@pytest.mark.asyncio
async def test_thinker_completion_applies_domain_directive_and_commits() -> None:
    unit = FakeThinkerUnitOfWork(thinker_context())
    handler = CompleteThinkerJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.directive == CompletionDirective.THINKER_EXECUTE
    assert unit.committed and unit.synchronized


@pytest.mark.asyncio
async def test_thinker_completion_preserves_manual_takeover() -> None:
    unit = FakeThinkerUnitOfWork(thinker_context(takeover=True))
    handler = CompleteThinkerJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.takeover and unit.committed and unit.synchronized
    assert unit.directive is None
