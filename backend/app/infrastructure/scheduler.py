import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import ValidationError

from app.application.dispatch_jobs import DispatchJobs
from app.application.jobs import (
    CompleteExecutorJob,
    CompleteFailedJob,
    CompleteIntakeJob,
    CompleteReviewerJob,
    CompleteTesterJob,
    CompleteThinkerJob,
)
from app.application.manage_worker_presence import ManageWorkerPresence
from app.application.ports.executor_completion import ExecutorCompletionCommand
from app.application.ports.intake_completion import IntakeCompletionCommand
from app.application.ports.job_completion import FailedJobCommand
from app.application.ports.job_dispatch import ClaimedJob
from app.application.ports.reviewer_completion import ReviewerCompletionCommand
from app.application.ports.tester_completion import TesterCompletionCommand
from app.application.ports.thinker_completion import ThinkerCompletionCommand
from app.application.ports.worker_runtime import WorkerRunner
from app.application.process_deliveries import ProcessDeliveries
from app.application.process_indexes import ProcessIndexes
from app.application.reconcile_tasks import ReconcileExternalTasks
from app.application.recover_resources import RecoveryManager
from app.application.run_startup_maintenance import RunStartupMaintenance
from app.config import Settings
from app.domain.agents import AgentRole
from app.domain.jobs import JobExecutionState
from app.schemas import WorkerResult

log = structlog.get_logger()


class Scheduler:
    def __init__(
        self,
        settings: Settings,
        worker_id: str,
        job_dispatch: DispatchJobs,
        worker_runner: WorkerRunner,
        failed_job_completer: CompleteFailedJob,
        intake_job_completer: CompleteIntakeJob,
        thinker_job_completer: CompleteThinkerJob,
        executor_job_completer: CompleteExecutorJob,
        tester_job_completer: CompleteTesterJob,
        reviewer_job_completer: CompleteReviewerJob,
        delivery_processor: ProcessDeliveries,
        index_processor: ProcessIndexes,
        startup_maintenance: RunStartupMaintenance,
        worker_presence: ManageWorkerPresence,
        task_reconciler: ReconcileExternalTasks,
        recovery_manager: RecoveryManager | None = None,
    ) -> None:
        self.settings = settings
        self._job_dispatch = job_dispatch
        self._worker_runner = worker_runner
        self._failed_job_completer = failed_job_completer
        self._intake_job_completer = intake_job_completer
        self._thinker_job_completer = thinker_job_completer
        self._executor_job_completer = executor_job_completer
        self._tester_job_completer = tester_job_completer
        self._reviewer_job_completer = reviewer_job_completer
        self._delivery_processor = delivery_processor
        self._index_processor = index_processor
        self._startup_maintenance = startup_maintenance
        self._worker_presence = worker_presence
        self._task_reconciler = task_reconciler
        self._recovery_manager = recovery_manager
        self.worker_id = worker_id
        self._stop = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._index_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._job_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        await self._startup_maintenance.execute()
        await self._worker_presence.online()
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
        await self._worker_presence.stopped()

    async def _run_heartbeat(self) -> None:
        while not self._stop.is_set():
            try:
                await self._worker_presence.online()
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
        try:
            while not self._stop.is_set():
                try:
                    self._job_tasks = {task for task in self._job_tasks if not task.done()}
                    await self._task_reconciler.execute()
                    if self._recovery_manager is not None:
                        await self._recovery_manager.recover_due_resources()
                    await self._delivery_processor.execute()
                    claimed_any = False
                    while len(self._job_tasks) < self.settings.scheduler_max_concurrent_jobs:
                        job = await self._job_dispatch.claim()
                        if job is None:
                            break
                        claimed_any = True
                        task = asyncio.create_task(
                            self._execute_safely(job), name=f"job-{job.job_id}"
                        )
                        self._job_tasks.add(task)
                    if self._job_tasks:
                        await asyncio.wait(
                            self._job_tasks,
                            timeout=self.settings.scheduler_poll_seconds,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                    elif not claimed_any:
                        await asyncio.sleep(self.settings.scheduler_poll_seconds)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("scheduler_iteration_failed")
                    await asyncio.sleep(self.settings.scheduler_poll_seconds)
        finally:
            if self._job_tasks:
                await asyncio.gather(*self._job_tasks, return_exceptions=True)
                self._job_tasks.clear()

    async def _execute_safely(self, claimed_job: ClaimedJob) -> None:
        try:
            await self._execute(claimed_job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("job_execution_failed", job_id=str(claimed_job.job_id))
            message = str(exc)
            failure = (
                message
                if message.startswith(("MODEL_POLICY_ERROR:", "MODEL_UNAVAILABLE:"))
                else f"Unknown system error: {type(exc).__name__}"
            )
            await self._finish(
                claimed_job.job_id,
                claimed_job.lease_token,
                JobExecutionState.FAILED,
                None,
                failure,
            )

    async def _run_indexer(self) -> None:
        while not self._stop.is_set():
            try:
                processed = await self._index_processor.execute()
                if not processed:
                    await asyncio.sleep(max(self.settings.scheduler_poll_seconds, 2.0))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("repository_index_iteration_failed")
                await asyncio.sleep(max(self.settings.scheduler_poll_seconds, 2.0))

    async def _execute(self, claimed_job: ClaimedJob) -> None:
        if not await self._job_dispatch.prepare(claimed_job):
            return
        job_id = claimed_job.job_id
        lease_token = claimed_job.lease_token
        if claimed_job.durable_result is not None:
            try:
                result = WorkerResult.model_validate(claimed_job.durable_result)
                if result.job_id != job_id:
                    raise ValueError("Durable worker result belongs to another Job")
            except (ValidationError, ValueError) as exc:
                await self._finish(
                    job_id,
                    lease_token,
                    JobExecutionState.FAILED,
                    None,
                    f"Invalid durable worker result: {exc}",
                )
                return
            await self._finish(
                job_id,
                lease_token,
                JobExecutionState.SUCCEEDED,
                result.model_dump(mode="json"),
                None,
            )
            if self._recovery_manager is not None:
                await self._recovery_manager.record_job_success(job_id)
            return
        execution = await self._worker_runner(job_id)
        if execution.timed_out:
            await self._finish(
                job_id,
                lease_token,
                JobExecutionState.TIMED_OUT,
                None,
                "Worker timed out",
            )
            return
        if execution.returncode != 0:
            reason = (
                execution.stderr.decode(errors="replace")[-4000:]
                or execution.stdout.decode(errors="replace")[-4000:]
                or f"Worker exited {execution.returncode}"
            )
            await self._finish(
                job_id,
                lease_token,
                JobExecutionState.FAILED,
                None,
                f"Worker crashed: {reason}",
            )
            return
        try:
            result = WorkerResult.model_validate_json(execution.stdout)
        except ValidationError as exc:
            await self._finish(
                job_id,
                lease_token,
                JobExecutionState.FAILED,
                None,
                f"Invalid worker result: {exc}",
            )
            return
        await self._finish(
            job_id,
            lease_token,
            JobExecutionState.SUCCEEDED,
            result.model_dump(mode="json"),
            None,
        )
        if self._recovery_manager is not None:
            await self._recovery_manager.record_job_success(job_id)

    async def _finish(
        self,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        state: JobExecutionState,
        result: dict[str, Any] | None,
        failure: str | None,
    ) -> None:
        if state != JobExecutionState.SUCCEEDED:
            completed = await self._failed_job_completer.execute(
                FailedJobCommand(
                    job_id=job_id,
                    lease_token=lease_token,
                    terminal_state=state.value,
                    failure=failure or state.value,
                    finished_at=datetime.now(UTC),
                )
            )
            if not completed:
                log.warning("stale_worker_result_rejected", job_id=str(job_id))
            return
        if result and result.get("role") == AgentRole.INTAKE.value:
            completed = await self._intake_job_completer.execute(
                IntakeCompletionCommand(job_id, lease_token, result, datetime.now(UTC))
            )
            if not completed:
                log.warning("stale_worker_result_rejected", job_id=str(job_id))
            return
        if result and result.get("role") == AgentRole.THINKER.value:
            completed = await self._thinker_job_completer.execute(
                ThinkerCompletionCommand(job_id, lease_token, result, datetime.now(UTC))
            )
            if not completed:
                log.warning("stale_worker_result_rejected", job_id=str(job_id))
            return
        if result and result.get("role") == AgentRole.EXECUTOR.value:
            completed = await self._executor_job_completer.execute(
                ExecutorCompletionCommand(job_id, lease_token, result, datetime.now(UTC))
            )
            if not completed:
                log.warning("stale_worker_result_rejected", job_id=str(job_id))
            return
        if result and result.get("role") == AgentRole.TESTER.value:
            completed = await self._tester_job_completer.execute(
                TesterCompletionCommand(job_id, lease_token, result, datetime.now(UTC))
            )
            if not completed:
                log.warning("stale_worker_result_rejected", job_id=str(job_id))
            return
        if result and result.get("role") == AgentRole.REVIEWER.value:
            completed = await self._reviewer_job_completer.execute(
                ReviewerCompletionCommand(job_id, lease_token, result, datetime.now(UTC))
            )
            if not completed:
                log.warning("stale_worker_result_rejected", job_id=str(job_id))
            return
        raise ValueError("Successful worker result is missing a supported role")
