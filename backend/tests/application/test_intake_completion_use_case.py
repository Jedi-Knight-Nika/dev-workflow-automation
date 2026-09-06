import types
import uuid
from datetime import UTC, datetime
from typing import Self

import pytest

from app.application.jobs import CompleteIntakeJob
from app.application.ports.intake_completion import (
    IntakeCompletionCommand,
    IntakeCompletionContext,
)
from app.domain.jobs import CompletionDirective


class FakeIntakeUnitOfWork:
    def __init__(self, context: IntakeCompletionContext | None) -> None:
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

    async def begin(self, _command: IntakeCompletionCommand) -> IntakeCompletionContext | None:
        return self.context

    async def finish_during_takeover(self, _context: IntakeCompletionContext) -> None:
        self.takeover = True

    async def apply(
        self, _context: IntakeCompletionContext, directive: CompletionDirective
    ) -> None:
        self.directive = directive

    async def commit(self) -> None:
        self.committed = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True


def intake_context(*, takeover: bool = False) -> IntakeCompletionContext:
    return IntakeCompletionContext(
        uuid.uuid4(),
        uuid.uuid4(),
        "INTERPRET_EXTERNAL_COMMENT",
        {"previous_state": "WAITING_GITHUB"},
        "EVENT_INTERPRETED",
        {"actionability": "INFORMATIONAL"},
        takeover,
    )


def command() -> IntakeCompletionCommand:
    return IntakeCompletionCommand(uuid.uuid4(), uuid.uuid4(), {}, datetime.now(UTC))


@pytest.mark.asyncio
async def test_intake_completion_applies_domain_directive_and_commits() -> None:
    unit = FakeIntakeUnitOfWork(intake_context())
    handler = CompleteIntakeJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.directive == CompletionDirective.INTAKE_INFORMATIONAL
    assert unit.committed and unit.synchronized


@pytest.mark.asyncio
async def test_intake_completion_preserves_manual_takeover() -> None:
    unit = FakeIntakeUnitOfWork(intake_context(takeover=True))
    handler = CompleteIntakeJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.takeover and unit.committed and unit.synchronized
    assert unit.directive is None
