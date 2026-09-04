import asyncio
import json
import os
import socket
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import ValidationError

from app.config import Settings
from app.db.models import Job, JobState, Task, TaskState
from app.db.session import SessionLocal
from app.schemas import WorkerResult
from app.services.events import broker
from app.services.orchestrator import claim_next_job, record_event, recover_expired_jobs

log = structlog.get_logger()


class Scheduler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._stop = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        async with SessionLocal() as session:
            await recover_expired_jobs(session)
        self._loop_task = asyncio.create_task(self._run(), name="job-scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._loop_task:
            await self._loop_task

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                async with SessionLocal() as session:
                    job = await claim_next_job(
                        session, self.worker_id, self.settings.worker_lease_seconds
                    )
                if job:
                    if job.lease_token is None:
                        raise RuntimeError("Claimed job is missing its lease token")
                    await self._execute(job.id, job.lease_token)
                else:
                    await asyncio.sleep(self.settings.scheduler_poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduler_iteration_failed")
                await asyncio.sleep(self.settings.scheduler_poll_seconds)

    async def _execute(self, job_id: uuid.UUID, lease_token: uuid.UUID) -> None:
        async with SessionLocal() as session:
            job = await session.get(Job, job_id)
            if job is None or job.lease_token != lease_token:
                return
            job.state = JobState.RUNNING
            await session.commit()
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.worker",
            str(job_id),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.settings.worker_timeout_seconds
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            await self._finish(job_id, lease_token, JobState.TIMED_OUT, None, "Worker timed out")
            return
        if process.returncode != 0:
            reason = (
                stderr.decode(errors="replace")[-4000:] or f"Worker exited {process.returncode}"
            )
            await self._finish(job_id, lease_token, JobState.FAILED, None, reason)
            return
        try:
            result = WorkerResult.model_validate_json(stdout)
        except ValidationError as exc:
            await self._finish(
                job_id, lease_token, JobState.FAILED, None, f"Invalid worker result: {exc}"
            )
            return
        await self._finish(
            job_id, lease_token, JobState.SUCCEEDED, result.model_dump(mode="json"), None
        )

    async def _finish(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        state: JobState,
        result: dict[str, Any] | None,
        failure: str | None,
    ) -> None:
        async with SessionLocal() as session:
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None or job.lease_token != lease_token:
                log.warning("stale_worker_result_rejected", job_id=str(job_id))
                return
            task = await session.get(Task, job.task_id, with_for_update=True)
            if task is None:
                raise RuntimeError(f"Task {job.task_id} disappeared while its job was running")
            job.state = state
            job.result = result
            job.failure_reason = failure
            job.finished_at = datetime.now(UTC)
            job.lease_expires_at = None
            if state == JobState.SUCCEEDED:
                if job.role.value == "THINKER":
                    task.state = TaskState.PLAN_READY
                elif job.role.value == "EXECUTOR":
                    task.state = TaskState.LOCAL_VALIDATION
                elif job.role.value == "REVIEWER":
                    task.state = TaskState.WAITING_GITHUB
                await record_event(
                    session,
                    task.id,
                    "JOB_SUCCEEDED",
                    {"job_id": str(job.id), "result": result.get("result") if result else None},
                )
            else:
                task.state = TaskState.NEEDS_HUMAN
                await record_event(
                    session,
                    task.id,
                    "JOB_FAILED",
                    {"job_id": str(job.id), "reason": failure or state.value},
                )
            await session.commit()
        await broker.publish(
            json.dumps({"type": "job.updated", "job_id": str(job_id), "state": state.value})
        )
