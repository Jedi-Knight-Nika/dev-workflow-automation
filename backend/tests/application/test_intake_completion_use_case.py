import types
import uuid
from datetime import UTC, datetime
from typing import Self

import pytest

from app.application.jobs import CompleteDelivererJob
from app.application.ports.deliverer_completion import (
    DelivererCompletionCommand,
    DelivererCompletionContext,
)
from app.domain.jobs import CompletionDirective


class FakeIntakeUnitOfWork:
    def __init__(self, context: DelivererCompletionContext | None) -> None:
        self.context = context
        self.directive: CompletionDirective | None = None
        self.takeover = False
        self.conversation = False
        self.committed = False
        self.external_actions_executed = False
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

    async def begin(
        self, _command: DelivererCompletionCommand
    ) -> DelivererCompletionContext | None:
        return self.context

    async def finish_during_takeover(self, _context: DelivererCompletionContext) -> None:
        self.takeover = True

    async def finish_conversation(self, _context: DelivererCompletionContext) -> None:
        self.conversation = True

    async def apply(
        self, _context: DelivererCompletionContext, directive: CompletionDirective
    ) -> None:
        self.directive = directive

    async def commit(self) -> None:
        self.committed = True

    async def execute_external_delivery_actions(self, _context: DelivererCompletionContext) -> None:
        self.external_actions_executed = True

    async def synchronize_tracker(self, _task_id: uuid.UUID) -> None:
        self.synchronized = True


def intake_context(*, takeover: bool = False) -> DelivererCompletionContext:
    return DelivererCompletionContext(
        uuid.uuid4(),
        uuid.uuid4(),
        "INTERPRET_EXTERNAL_COMMENT",
        {"previous_state": "WAITING_GITHUB"},
        "EVENT_INTERPRETED",
        {"actionability": "INFORMATIONAL"},
        takeover,
    )


def conversation_context() -> DelivererCompletionContext:
    return DelivererCompletionContext(
        uuid.uuid4(),
        uuid.uuid4(),
        "RESPOND_TO_MESSAGE",
        {"conversation_only": True},
        "EVENT_INTERPRETED",
        {"actionability": "INFORMATIONAL"},
        False,
    )


def command() -> DelivererCompletionCommand:
    return DelivererCompletionCommand(uuid.uuid4(), uuid.uuid4(), {}, datetime.now(UTC))


@pytest.mark.asyncio
async def test_deliverer_completion_applies_domain_directive_and_commits() -> None:
    unit = FakeIntakeUnitOfWork(intake_context())
    handler = CompleteDelivererJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.directive == CompletionDirective.DELIVERER_INFORMATIONAL
    assert unit.committed and unit.external_actions_executed and unit.synchronized


@pytest.mark.asyncio
async def test_deliverer_completion_preserves_manual_takeover() -> None:
    unit = FakeIntakeUnitOfWork(intake_context(takeover=True))
    handler = CompleteDelivererJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.takeover and unit.committed and unit.synchronized
    assert not unit.external_actions_executed
    assert unit.directive is None


@pytest.mark.asyncio
async def test_conversation_response_does_not_apply_workflow_directive() -> None:
    unit = FakeIntakeUnitOfWork(conversation_context())
    handler = CompleteDelivererJob(lambda: unit)  # type: ignore[arg-type]

    assert await handler.execute(command())
    assert unit.conversation and unit.committed and unit.synchronized
    assert unit.directive is None
    assert not unit.external_actions_executed
