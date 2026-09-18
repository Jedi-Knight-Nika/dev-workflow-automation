import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.coordinator.application.ports import ConversationUnavailable, SituationChanged
from app.coordinator.application.process import ProcessCoordinator
from app.coordinator.domain.protocol import Checkpoint, Decision, Directive


def setup_process():
    claimed = (uuid4(), uuid4(), "dashboard", {})
    runs = AsyncMock(claim=AsyncMock(return_value=claimed))
    decision = Decision(1, Directive.WAIT, "", "", "", (), (), Checkpoint("", (), ()))
    model = AsyncMock(decide=AsyncMock(return_value=decision))
    conversations = AsyncMock()
    process = ProcessCoordinator(runs, model, conversations, watch_seconds=0.001)
    return process, runs, model, conversations, decision, claimed


async def test_no_claim_means_no_model_call():
    process, runs, model, _, _, _ = setup_process()
    runs.claim.return_value = None
    assert not await process.process_one()
    model.decide.assert_not_awaited()


async def test_decision_is_saved_through_port_without_a_database():
    process, runs, model, _, decision, claimed = setup_process()
    assert await process.process_one()
    model.decide.assert_awaited_once_with(claimed[0], claimed[3], 0)
    runs.complete.assert_awaited_once_with(claimed[0], claimed[1], decision, claimed[3])
    runs.fail.assert_not_awaited()


async def test_context_expansion_is_deduplicated_and_bounded():
    process, runs, model, conversations, decision, claimed = setup_process()
    model.decide.side_effect = [replace(decision, read_tools=("READ_TASK", "READ_TASK")), decision]
    conversations.read.side_effect = ConversationUnavailable("ReadTimeout")
    assert await process.process_one()
    conversations.read.assert_awaited_once()
    assert model.decide.await_count == 2
    assert claimed[3]["requested_evidence"] == {"READ_TASK": {"unavailable": "ReadTimeout"}}
    runs.complete.assert_awaited_once()


async def test_repeated_context_requests_fail_without_a_third_model_call():
    process, runs, model, _, decision, _ = setup_process()
    model.decide.return_value = replace(decision, read_tools=("READ_TASK",))
    assert await process.process_one()
    assert model.decide.await_count == 2
    runs.complete.assert_not_awaited()
    assert runs.fail.await_args.kwargs == {"superseded": False}


@pytest.mark.parametrize("superseded", [True, False])
async def test_authority_change_cancels_inference(superseded):
    process, runs, model, _, _, _ = setup_process()
    cancelled = asyncio.Event()

    async def wait(*_args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    model.decide.side_effect = wait
    runs.ensure_authorized.side_effect = SituationChanged() if superseded else ValueError()
    assert await asyncio.wait_for(process.process_one(), timeout=1)
    assert cancelled.is_set()
    assert runs.fail.await_args.kwargs == {"superseded": superseded}
    runs.complete.assert_not_awaited()


async def test_cancellation_records_failure_and_propagates():
    process, runs, model, _, _, _ = setup_process()
    started = asyncio.Event()

    async def wait(*_args):
        started.set()
        await asyncio.Event().wait()

    model.decide.side_effect = wait
    running = asyncio.create_task(process.process_one())
    await asyncio.wait_for(started.wait(), timeout=1)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    runs.fail.assert_awaited_once()
    assert runs.fail.await_args.args[1] == "CancelledError"


async def test_timeout_preserves_bounded_execution():
    process, runs, model, _, _, _ = setup_process()
    process.timeout_seconds = 0.01

    async def wait(*_args):
        await asyncio.Event().wait()

    model.decide.side_effect = wait
    assert await asyncio.wait_for(process.process_one(), timeout=1)
    assert runs.fail.await_args.args[1] == "TimeoutError"
