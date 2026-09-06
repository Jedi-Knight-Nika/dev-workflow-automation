import asyncio
import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.application.ports.job_dispatch import ClaimedJob
from app.domain.operational_states import JobRole
from app.infrastructure.scheduler import Scheduler, parse_worker_result
from app.schemas import WorkerResult


def test_worker_result_parser_uses_final_json_line_after_process_logs() -> None:
    job_id = uuid.uuid4()
    task_id = uuid.uuid4()
    worker_result = WorkerResult(
        job_id=job_id,
        task_id=task_id,
        role=JobRole.INTAKE,
        result="INTAKE_COMPLETE",
        summary="ready",
    )
    stdout = b"HTTP Request: POST https://api.openai.com/v1/responses 200 OK\n"
    stdout += worker_result.model_dump_json().encode()

    result = parse_worker_result(stdout)

    assert result.job_id == job_id
    assert result.task_id == task_id


class PreparedDispatch:
    async def prepare(self, _job: ClaimedJob) -> bool:
        return True


class InvalidConfigurationDispatch:
    async def prepare(self, _job: ClaimedJob) -> bool:
        raise RuntimeError("MODEL_POLICY_ERROR: Agent model is not configured")


class ForbiddenRunner:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, _job_id: uuid.UUID) -> None:
        self.called = True
        raise AssertionError("A durable result must not launch another worker")


class RecordingCompleter:
    def __init__(self) -> None:
        self.commands: list[object] = []

    async def execute(self, command: object) -> bool:
        self.commands.append(command)
        return True


@pytest.mark.asyncio
async def test_reclaimed_job_resumes_durable_result_without_worker_execution() -> None:
    job_id = uuid.uuid4()
    task_id = uuid.uuid4()
    lease_token = uuid.uuid4()
    runner = ForbiddenRunner()
    executor_completer = RecordingCompleter()
    unused = cast(Any, object())
    scheduler = Scheduler(
        unused,
        "test-scheduler",
        cast(Any, PreparedDispatch()),
        cast(Any, runner),
        unused,
        unused,
        unused,
        cast(Any, executor_completer),
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
    )
    claimed = ClaimedJob(
        job_id,
        lease_token,
        {
            "protocol_version": 1,
            "job_id": str(job_id),
            "task_id": str(task_id),
            "role": JobRole.EXECUTOR.value,
            "result": "IMPLEMENTED",
            "summary": "Already completed",
            "data": {"changed_files": ["src/example.py"]},
        },
    )

    await scheduler._execute(claimed)

    assert not runner.called
    assert len(executor_completer.commands) == 1


@pytest.mark.asyncio
async def test_scheduler_runs_jobs_up_to_configured_bound() -> None:
    jobs = [ClaimedJob(uuid.uuid4(), uuid.uuid4()), ClaimedJob(uuid.uuid4(), uuid.uuid4())]

    class Dispatch:
        async def claim(self) -> ClaimedJob | None:
            return jobs.pop(0) if jobs else None

    class NoOp:
        async def execute(self) -> None:
            return None

    settings = SimpleNamespace(scheduler_max_concurrent_jobs=2, scheduler_poll_seconds=0.01)
    unused = cast(Any, object())
    scheduler = Scheduler(
        cast(Any, settings),
        "test-scheduler",
        cast(Any, Dispatch()),
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
        cast(Any, NoOp()),
        unused,
        unused,
        unused,
        cast(Any, NoOp()),
    )
    release = asyncio.Event()
    both_started = asyncio.Event()
    active = 0
    peak = 0

    async def execute(_job: ClaimedJob) -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            both_started.set()
        await release.wait()
        active -= 1

    scheduler._execute = execute  # type: ignore[method-assign]
    run_task = asyncio.create_task(scheduler._run())
    await asyncio.wait_for(both_started.wait(), timeout=1)
    scheduler._stop.set()
    release.set()
    await asyncio.wait_for(run_task, timeout=1)

    assert peak == 2


@pytest.mark.asyncio
async def test_preflight_configuration_error_is_preserved_for_resilience_routing() -> None:
    job = ClaimedJob(uuid.uuid4(), uuid.uuid4())
    failed_completer = RecordingCompleter()
    runner = ForbiddenRunner()
    unused = cast(Any, object())
    scheduler = Scheduler(
        unused,
        "test-scheduler",
        cast(Any, InvalidConfigurationDispatch()),
        cast(Any, runner),
        cast(Any, failed_completer),
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
        unused,
    )

    await scheduler._execute_safely(job)

    assert not runner.called
    command = cast(Any, failed_completer.commands[0])
    assert command.failure == "MODEL_POLICY_ERROR: Agent model is not configured"
