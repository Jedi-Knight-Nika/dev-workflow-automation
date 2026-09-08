import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.engineering.application.jobs import PhaseLease
from app.platform.configuration.settings import Settings
from app.platform.scheduling.scheduler import Scheduler


def controller() -> Scheduler:
    return Scheduler(
        settings=Settings(
            _env_file=None,
            scheduler_poll_seconds=0.01,
            scheduler_max_concurrent_jobs=2,
            worker_heartbeat_seconds=0.01,
        ),
        worker_id="test-controller",
        jobs=cast(Any, AsyncMock(claim=AsyncMock(return_value=None))),
        worker=cast(Any, AsyncMock()),
        deliveries=cast(Any, AsyncMock()),
        presence=cast(Any, AsyncMock()),
        reconciler=cast(Any, AsyncMock()),
    )


def lease() -> PhaseLease:
    return PhaseLease(uuid4(), uuid4(), uuid4(), "DEVELOPER_TURN", 1)


@pytest.mark.asyncio
async def test_start_recovers_before_claiming_and_does_not_start_a_legacy_worker() -> None:
    scheduler = controller()
    order: list[str] = []
    scheduler.jobs.recover.side_effect = lambda: order.append("recover")
    scheduler.jobs.claim.side_effect = lambda: order.append("claim")
    await scheduler.start()
    try:
        await asyncio.sleep(0.03)
        assert order[0] == "recover"
        assert "claim" in order
        assert not hasattr(scheduler, "_worker_runner")
        assert not hasattr(scheduler, "_index_task")
        with pytest.raises(RuntimeError, match="already started"):
            await scheduler.start()
    finally:
        await scheduler.stop()
    scheduler.presence.stopped.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduler_obeys_concurrency_and_cancels_active_turns_on_stop() -> None:
    scheduler = controller()
    scheduler.jobs.claim.side_effect = [lease(), lease(), lease(), None]
    started = asyncio.Event()
    cancelled: list[PhaseLease] = []
    active = 0

    async def execute(item: PhaseLease) -> None:
        nonlocal active
        active += 1
        if active == 2:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(item)
            active -= 1

    scheduler.worker.execute.side_effect = execute
    await scheduler.start()
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.sleep(0.03)
        assert active == 2
        assert scheduler.jobs.claim.await_count == 2
    finally:
        await asyncio.wait_for(scheduler.stop(), timeout=1)
    assert active == 0
    assert len(cancelled) == 2
    assert not scheduler._job_tasks


@pytest.mark.asyncio
async def test_stop_interrupts_hung_external_polling() -> None:
    scheduler = controller()
    started = asyncio.Event()

    async def hanging_poll() -> None:
        started.set()
        await asyncio.Event().wait()

    scheduler.reconciler.execute.side_effect = hanging_poll
    await scheduler.start()
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.wait_for(scheduler.stop(), timeout=1)
    scheduler.jobs.claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_start_does_not_mark_worker_online_or_launch_tasks() -> None:
    scheduler = controller()
    scheduler.jobs.recover.side_effect = RuntimeError("storage unavailable")
    with pytest.raises(RuntimeError, match="storage unavailable"):
        await scheduler.start()
    assert scheduler._loop_task is None
    scheduler.presence.online.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_process_never_constructs_scheduler(monkeypatch, tmp_path) -> None:
    from app import scheduler_runner

    settings = Settings(_env_file=None, scheduler_enabled=False, workspace_root=tmp_path / "unused")
    monkeypatch.setattr(scheduler_runner, "get_settings", lambda: settings)

    def forbidden(_settings):
        pytest.fail("Disabled worker constructed a scheduler")

    monkeypatch.setattr(scheduler_runner, "create_scheduler", forbidden)
    # No real process signals in a unit test; the event stays asleep until cancellation.
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", lambda *_args: None)
    running = asyncio.create_task(scheduler_runner.run())
    await asyncio.sleep(0.01)
    assert not running.done()
    assert not settings.workspace_root.exists()
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
