import asyncio
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Job, JobRole, JobState, Repository, Task, TaskState, WorkerNode
from app.db.session import SessionLocal
from app.schemas import WorkerResult
from app.services.github_events import process_next_github_delivery
from app.services.indexing import process_queued_indexes
from app.services.linear_events import process_next_linear_delivery
from app.services.linear_sync import sync_current_task_state_to_linear
from app.services.orchestrator import (
    acquire_workspace_lease,
    claim_next_job,
    enqueue_job,
    record_event,
    recover_expired_jobs,
    release_workspace_lease,
)
from app.services.pull_requests import publish_pull_request
from app.services.reconciliation import reconcile_startup
from app.services.reviews import persist_review_result
from app.services.worker_transport import run_worker

log = structlog.get_logger()


def retry_delay(base_seconds: int, attempt: int) -> int:
    return base_seconds * (1 << max(attempt - 1, 0))


class Scheduler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}"
        self._stop = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._index_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        async with SessionLocal() as session:
            await recover_expired_jobs(session)
            await reconcile_startup(session)
            await self._write_worker_state(session, "ONLINE")
        self._loop_task = asyncio.create_task(self._run(), name="job-scheduler")
        self._index_task = asyncio.create_task(self._run_indexer(), name="repository-indexer")
        self._heartbeat_task = asyncio.create_task(self._run_heartbeat(), name="worker-heartbeat")

    async def stop(self) -> None:
        self._stop.set()
        if self._loop_task:
            await self._loop_task
        if self._index_task:
            await self._index_task
        if self._heartbeat_task:
            await self._heartbeat_task
        async with SessionLocal() as session:
            await self._write_worker_state(session, "STOPPED")

    async def _write_worker_state(self, session: AsyncSession, status: str) -> None:
        now = datetime.now(UTC)
        worker = await session.get(WorkerNode, self.worker_id)
        if worker is None:
            worker = WorkerNode(
                id=self.worker_id,
                hostname=socket.gethostname(),
                process_id=os.getpid(),
                capabilities=["jobs", "linear", "indexing"],
                started_at=now,
            )
            session.add(worker)
        worker.status = status
        worker.last_heartbeat = now
        worker.stopped_at = now if status == "STOPPED" else None
        await session.commit()

    async def _run_heartbeat(self) -> None:
        while not self._stop.is_set():
            try:
                async with SessionLocal() as session:
                    await self._write_worker_state(session, "ONLINE")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("worker_heartbeat_failed", worker_id=self.worker_id)
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.settings.worker_heartbeat_seconds
                )
            except TimeoutError:
                pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                async with SessionLocal() as session:
                    await process_next_linear_delivery(session)
                    await process_next_github_delivery(session)
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

    async def _run_indexer(self) -> None:
        while not self._stop.is_set():
            try:
                async with SessionLocal() as session:
                    processed = await process_queued_indexes(session)
                if not processed:
                    await asyncio.sleep(max(self.settings.scheduler_poll_seconds, 2.0))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("repository_index_iteration_failed")
                await asyncio.sleep(max(self.settings.scheduler_poll_seconds, 2.0))

    async def _execute(self, job_id: uuid.UUID, lease_token: uuid.UUID) -> None:
        async with SessionLocal() as session:
            job = await session.get(Job, job_id)
            if job is None or job.lease_token != lease_token:
                return
            if job.role.value == "EXECUTOR" and not await acquire_workspace_lease(
                session, job, self.settings.worker_lease_seconds
            ):
                job.state = JobState.QUEUED
                job.worker_id = None
                job.lease_token = None
                job.lease_expires_at = None
                await session.commit()
                return
            job.state = JobState.RUNNING
            await session.commit()
        execution = await run_worker(self.settings, job_id)
        if execution.timed_out:
            await self._finish(job_id, lease_token, JobState.TIMED_OUT, None, "Worker timed out")
            return
        if execution.returncode != 0:
            reason = (
                execution.stderr.decode(errors="replace")[-4000:]
                or execution.stdout.decode(errors="replace")[-4000:]
                or f"Worker exited {execution.returncode}"
            )
            await self._finish(job_id, lease_token, JobState.FAILED, None, reason)
            return
        try:
            result = WorkerResult.model_validate_json(execution.stdout)
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
        publish_task_id: uuid.UUID | None = None
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
            await release_workspace_lease(session, job)
            if task.manual_takeover:
                await record_event(
                    session,
                    task.id,
                    "JOB_FINISHED_DURING_TAKEOVER",
                    {"job_id": str(job.id), "state": state.value},
                )
            elif state == JobState.SUCCEEDED:
                outcome = result.get("result") if result else None
                if job.role == JobRole.INTAKE:
                    intake = (result or {}).get("data", {})
                    if (
                        outcome != "EVENT_INTERPRETED"
                        or intake.get("actionability") == "NEEDS_HUMAN"
                    ):
                        task.state = TaskState.NEEDS_HUMAN
                        await record_event(
                            session,
                            task.id,
                            "INTAKE_NEEDS_HUMAN",
                            {"job_id": str(job.id), "interpretation": intake},
                        )
                    else:
                        await record_event(
                            session,
                            task.id,
                            "INTAKE_INTERPRETED",
                            {"job_id": str(job.id), "interpretation": intake},
                        )
                        if (
                            job.action == "INTERPRET_EXTERNAL_COMMENT"
                            and intake.get("actionability") == "INFORMATIONAL"
                        ):
                            previous_state = job.payload.get("previous_state")
                            task.state = (
                                TaskState(previous_state)
                                if isinstance(previous_state, str)
                                else TaskState.WAITING_GITHUB
                            )
                        elif (
                            job.action == "INTERPRET_EXTERNAL_COMMENT"
                            and intake.get("event_type") == "REVIEW_FIX"
                        ):
                            await self._enqueue_executor_repair(
                                session,
                                task,
                                "REPAIR_EXTERNAL_FEEDBACK",
                                {"intake": intake, "external_comment": job.payload},
                            )
                        elif job.action == "INTERPRET_EXTERNAL_COMMENT":
                            await self._enqueue_replan(
                                session,
                                task,
                                {"intake": intake, "external_comment": job.payload},
                            )
                        else:
                            await enqueue_job(
                                session,
                                task,
                                JobRole.THINKER,
                                "CREATE_PLAN",
                                payload={"intake": intake},
                            )
                elif job.role == JobRole.THINKER:
                    if outcome == "PLAN_READY":
                        task.state = TaskState.PLAN_READY
                        if task.repository_id:
                            await enqueue_job(session, task, JobRole.EXECUTOR, "IMPLEMENT_PLAN")
                    elif outcome == "NEEDS_CONTEXT":
                        task.state = TaskState.CONTEXT_PENDING
                        await record_event(
                            session,
                            task.id,
                            "THINKER_NEEDS_CONTEXT",
                            {"job_id": str(job.id), "details": (result or {}).get("data", {})},
                        )
                    else:
                        task.state = TaskState.NEEDS_HUMAN
                        await record_event(
                            session,
                            task.id,
                            "THINKER_NEEDS_HUMAN",
                            {"job_id": str(job.id), "details": (result or {}).get("data", {})},
                        )
                elif job.role == JobRole.EXECUTOR:
                    if outcome == "IMPLEMENTED":
                        task.state = TaskState.LOCAL_VALIDATION
                        await enqueue_job(
                            session,
                            task,
                            JobRole.REVIEWER,
                            "REVIEW_CHANGES",
                            payload=result or {},
                        )
                    elif outcome == "TEST_FAILED":
                        await self._enqueue_executor_repair(
                            session, task, "REPAIR_LOCAL_VALIDATION", result or {}
                        )
                    elif outcome in {"PLAN_MISMATCH", "NEEDS_REPLAN"}:
                        await self._enqueue_replan(session, task, result or {})
                    else:
                        task.state = TaskState.NEEDS_HUMAN
                        await record_event(
                            session,
                            task.id,
                            "EXECUTOR_NEEDS_HUMAN",
                            {
                                "job_id": str(job.id),
                                "outcome": outcome,
                                "details": (result or {}).get("data", {}),
                            },
                        )
                elif job.role == JobRole.REVIEWER:
                    repeat_count = await persist_review_result(session, job, result or {})
                    if outcome == "PASS":
                        task.state = TaskState.WAITING_GITHUB
                        if task.repository_id and task.workspace_path:
                            publish_task_id = task.id
                    elif repeat_count >= self.settings.max_same_finding_repeats:
                        task.state = TaskState.NEEDS_HUMAN
                        await record_event(
                            session,
                            task.id,
                            "REPEATED_FINDING_LIMIT_REACHED",
                            {
                                "job_id": str(job.id),
                                "occurrences": repeat_count,
                                "limit": self.settings.max_same_finding_repeats,
                            },
                        )
                    elif outcome == "FAIL_ACTIONABLE":
                        await self._enqueue_executor_repair(
                            session, task, "REPAIR_INTERNAL_REVIEW", result or {}
                        )
                    elif outcome == "FAIL_ARCHITECTURAL":
                        await self._enqueue_replan(session, task, result or {})
                    else:
                        task.state = TaskState.NEEDS_HUMAN
                        await record_event(
                            session,
                            task.id,
                            "REVIEW_NEEDS_HUMAN",
                            {
                                "job_id": str(job.id),
                                "outcome": outcome,
                                "details": (result or {}).get("data", {}),
                            },
                        )
                await record_event(
                    session,
                    task.id,
                    "JOB_SUCCEEDED",
                    {"job_id": str(job.id), "result": result.get("result") if result else None},
                )
            else:
                if job.attempt < self.settings.max_job_attempts:
                    delay = retry_delay(self.settings.job_retry_base_seconds, job.attempt)
                    job.state = JobState.RETRY_WAIT
                    job.worker_id = None
                    job.lease_token = None
                    job.retry_not_before = datetime.now(UTC) + timedelta(seconds=delay)
                    await record_event(
                        session,
                        task.id,
                        "JOB_RETRY_SCHEDULED",
                        {
                            "job_id": str(job.id),
                            "attempt": job.attempt,
                            "max_attempts": self.settings.max_job_attempts,
                            "delay_seconds": delay,
                            "reason": failure or state.value,
                        },
                    )
                else:
                    task.state = TaskState.NEEDS_HUMAN
                    await record_event(
                        session,
                        task.id,
                        "JOB_FAILED",
                        {
                            "job_id": str(job.id),
                            "attempts": job.attempt,
                            "reason": failure or state.value,
                        },
                    )
            await session.commit()
        if publish_task_id:
            await self._publish_reviewed_task(publish_task_id)
        else:
            async with SessionLocal() as session:
                completed_task = await session.get(Task, job.task_id)
                if completed_task:
                    await sync_current_task_state_to_linear(session, completed_task)

    async def _publish_reviewed_task(self, task_id: uuid.UUID) -> None:
        try:
            async with SessionLocal() as session:
                task = await session.get(Task, task_id, with_for_update=True)
                if (
                    task is None
                    or task.state != TaskState.WAITING_GITHUB
                    or task.manual_takeover
                    or task.repository_id is None
                ):
                    return
                repository = await session.get(Repository, task.repository_id)
                if repository is None or not repository.enabled:
                    raise RuntimeError("Reviewed task repository is unavailable")
                await publish_pull_request(session, task, repository)
        except Exception as exc:
            log.exception("automatic_pull_request_publish_failed", task_id=str(task_id))
            async with SessionLocal() as session:
                task = await session.get(Task, task_id, with_for_update=True)
                if task is None:
                    return
                task.state = TaskState.NEEDS_HUMAN
                await record_event(
                    session,
                    task.id,
                    "AUTOMATIC_PR_PUBLISH_FAILED",
                    {"error": str(exc)[:1000]},
                )
                await session.commit()

    async def _enqueue_executor_repair(
        self, session: AsyncSession, task: Task, action: str, payload: dict[str, Any]
    ) -> None:
        total = await session.scalar(
            select(func.count(Job.id)).where(Job.task_id == task.id, Job.role == JobRole.EXECUTOR)
        )
        if (total or 0) >= self.settings.max_executor_jobs_per_task:
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session,
                task.id,
                "REPAIR_LIMIT_REACHED",
                {"limit": self.settings.max_executor_jobs_per_task},
            )
            return
        await enqueue_job(session, task, JobRole.EXECUTOR, action, payload=payload)

    async def _enqueue_replan(
        self, session: AsyncSession, task: Task, executor_result: dict[str, Any]
    ) -> None:
        total = await session.scalar(
            select(func.count(Job.id)).where(Job.task_id == task.id, Job.role == JobRole.THINKER)
        )
        if (total or 0) >= self.settings.max_thinker_jobs_per_task:
            task.state = TaskState.NEEDS_HUMAN
            await record_event(
                session,
                task.id,
                "REPLAN_LIMIT_REACHED",
                {"limit": self.settings.max_thinker_jobs_per_task},
            )
            return
        task.state = TaskState.PLANNING
        await enqueue_job(
            session,
            task,
            JobRole.THINKER,
            "REVISE_PLAN",
            payload={"executor_result": executor_result},
        )
        await record_event(
            session,
            task.id,
            "REPLAN_QUEUED",
            {"attempt": (total or 0) + 1},
        )
