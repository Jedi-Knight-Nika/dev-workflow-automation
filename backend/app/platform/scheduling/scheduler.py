"""Bounded phase dispatch and external-event polling; no model-call loop."""

import asyncio
from collections.abc import Callable
from time import monotonic
from typing import Protocol

import structlog

from app.engineering.application.jobs import PhaseJobs, RunEngineeringJob
from app.intake.application.process_deliveries import ProcessDeliveries
from app.intake.application.reconcile_tasks import ReconcileExternalTasks
from app.platform.scheduling.manage_worker_presence import ManageWorkerPresence

log = structlog.get_logger()


class SchedulerSettings(Protocol):
    @property
    def scheduler_poll_seconds(self) -> float: ...
    @property
    def scheduler_max_concurrent_jobs(self) -> int: ...
    @property
    def worker_lease_seconds(self) -> int: ...
    @property
    def worker_heartbeat_seconds(self) -> float: ...


class Scheduler:
    def __init__(
        self,
        *,
        settings: SchedulerSettings,
        worker_id: str,
        jobs: PhaseJobs,
        worker: RunEngineeringJob,
        deliveries: ProcessDeliveries,
        presence: ManageWorkerPresence,
        reconciler: ReconcileExternalTasks,
        observe_claim: Callable[[bool, float], None] | None = None,
    ) -> None:
        self.settings, self.worker_id = settings, worker_id
        self.jobs, self.worker = jobs, worker
        self.deliveries, self.presence, self.reconciler = deliveries, presence, reconciler
        self.observe_claim = observe_claim
        self._stop = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._integration_task: asyncio.Task[None] | None = None
        self._job_tasks: set[asyncio.Task[None]] = set()
        self._last_recovery = 0.0

    async def start(self) -> None:
        if self._loop_task is not None:
            raise RuntimeError("Scheduler is already started")
        self._stop.clear()
        # Reconcile lost leases/cost receipts before admitting any new paid turn.
        await self.jobs.recover()
        self._last_recovery = monotonic()
        await self.presence.online()
        self._loop_task = asyncio.create_task(self._run(), name="phase-scheduler")
        self._integration_task = asyncio.create_task(
            self._integrations(), name="integration-polling"
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat(), name="worker-heartbeat")

    async def stop(self) -> None:
        self._stop.set()
        # Polling HTTP calls must not postpone cancellation of paid native turns.
        background = [
            task for task in (self._loop_task, self._heartbeat_task, self._integration_task) if task
        ]
        running = list(self._job_tasks)
        for task in (*background, *running):
            task.cancel()
        await asyncio.gather(*background, *running, return_exceptions=True)
        self._job_tasks.clear()
        self._loop_task = self._heartbeat_task = self._integration_task = None
        await self.presence.stopped()

    async def _wait(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def _heartbeat(self) -> None:
        while not self._stop.is_set():
            try:
                await self.presence.online()
            except Exception:
                log.exception("worker_heartbeat_failed", worker_id=self.worker_id)
            await self._wait(self.settings.worker_heartbeat_seconds)

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._job_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            # RunEngineeringJob normally records failures. A storage failure can
            # still escape; observe it, leaving lease recovery to suspend the job.
            log.error("phase_controller_failed", task=task.get_name())

    async def _integrations(self) -> None:
        # Provider latency must not hold up independent engineering job admission.
        while not self._stop.is_set():
            try:
                await self.reconciler.execute()
                await self.deliveries.execute()
            except Exception:
                log.exception("integration_iteration_failed")
            await self._wait(self.settings.scheduler_poll_seconds)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                if monotonic() - self._last_recovery >= self.settings.worker_lease_seconds:
                    await self.jobs.recover()
                    self._last_recovery = monotonic()
                while (
                    not self._stop.is_set()
                    and len(self._job_tasks) < self.settings.scheduler_max_concurrent_jobs
                ):
                    started = monotonic()
                    lease = await self.jobs.claim()
                    if self.observe_claim is not None:
                        self.observe_claim(lease is not None, monotonic() - started)
                    if lease is None:
                        break
                    task = asyncio.create_task(
                        self.worker.execute(lease), name=f"phase-{lease.job_id}"
                    )
                    self._job_tasks.add(task)
                    task.add_done_callback(self._finished)
            except Exception:
                log.exception("scheduler_iteration_failed")
            await self._wait(self.settings.scheduler_poll_seconds)
