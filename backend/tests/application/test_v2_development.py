from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.usage import Usage
from app.engineering.application.develop import (
    DevelopmentBlocked,
    DevelopmentStore,
    DevelopTask,
    SessionContext,
)


def dependencies() -> tuple[AsyncMock, AsyncMock]:
    harness, store = AsyncMock(), AsyncMock(spec=DevelopmentStore)
    harness.start.return_value = "native-123"
    harness.run_turn.return_value = TurnReceipt(
        "native-123", "turn-1", "Tests passed", "completed", Usage(10, 5, 0, 0)
    )
    store.consumed_cost.return_value = Decimal(0)
    store.begin_run.return_value = uuid4()
    return harness, store


@pytest.mark.asyncio
async def test_developer_persists_native_id_before_coding() -> None:
    harness, store = dependencies()
    context = SessionContext(uuid4(), None, 1, "Implement the task")

    async def code(prompt: str) -> TurnReceipt:
        store.session_started.assert_awaited_once_with(context.task_id, "native-123")
        return TurnReceipt("native-123", "turn-1", prompt, "completed", Usage())

    harness.run_turn.side_effect = code
    await DevelopTask(harness, store, Decimal(5)).execute(context)
    harness.start.assert_awaited_once()
    harness.resume.assert_not_called()
    store.finish_run.assert_awaited_once()
    harness.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_repair_resumes_same_session_and_sends_only_feedback_delta() -> None:
    harness, store = dependencies()
    context = SessionContext(uuid4(), "native-123", 3, "OLD HUGE REQUEST", "old checkpoint")
    await DevelopTask(harness, store, Decimal(5)).execute(
        context, feedback="Fix test_login assertion"
    )
    harness.start.assert_not_called()
    harness.resume.assert_awaited_once_with("native-123")
    harness.run_turn.assert_awaited_once_with("Fix test_login assertion")


@pytest.mark.asyncio
async def test_compaction_is_a_separately_accounted_run_on_the_same_session() -> None:
    harness, store = dependencies()
    harness.compact.return_value = harness.run_turn.return_value
    await DevelopTask(harness, store, Decimal(5)).execute(
        SessionContext(uuid4(), "native-123", 1, "Old request"),
        feedback="New feedback",
        compaction=True,
    )
    harness.resume.assert_awaited_once_with("native-123")
    harness.compact.assert_awaited_once()
    harness.run_turn.assert_not_awaited()
    store.begin_run.assert_awaited_once()
    store.finish_run.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("consumed", [None, Decimal(5), Decimal(7)])
async def test_no_paid_call_when_budget_is_exhausted_or_unknown(consumed: Decimal | None) -> None:
    harness, store = dependencies()
    store.consumed_cost.return_value = consumed
    with pytest.raises(DevelopmentBlocked):
        await DevelopTask(harness, store, Decimal(5)).execute(
            SessionContext(uuid4(), None, 1, "Do it")
        )
    harness.start.assert_not_called()
    store.begin_run.assert_not_called()


@pytest.mark.asyncio
async def test_missing_session_cannot_silently_restart_repair() -> None:
    harness, store = dependencies()
    with pytest.raises(DevelopmentBlocked, match="persisted"):
        await DevelopTask(harness, store, Decimal(5)).execute(
            SessionContext(uuid4(), None, 1, "Do it"), feedback="Fix"
        )
    harness.run_turn.assert_not_called()


@pytest.mark.asyncio
async def test_failure_is_recorded_without_retrying_a_fresh_session() -> None:
    harness, store = dependencies()
    harness.run_turn.side_effect = TimeoutError("provider did not finish")
    with pytest.raises(TimeoutError):
        await DevelopTask(harness, store, Decimal(5)).execute(
            SessionContext(uuid4(), "native-123", 1, "Do it")
        )
    store.fail_run.assert_awaited_once_with(
        store.begin_run.return_value, "TimeoutError", inference_started=True
    )
    harness.run_turn.assert_awaited_once()
    harness.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_pre_turn_failure_is_distinguished_from_unknown_paid_usage() -> None:
    harness, store = dependencies()
    harness.start.side_effect = RuntimeError("Container configuration unavailable")
    with pytest.raises(RuntimeError):
        await DevelopTask(harness, store, Decimal(5)).execute(
            SessionContext(uuid4(), None, 1, "Do it")
        )
    store.fail_run.assert_awaited_once_with(
        store.begin_run.return_value, "RuntimeError", inference_started=False
    )
    harness.run_turn.assert_not_called()
    harness.close.assert_awaited_once()
