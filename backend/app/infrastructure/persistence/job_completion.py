import hashlib
import types
import uuid
from datetime import timedelta
from typing import Self

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.job_completion import FailedJobCommand, FailedJobContext
from app.application.ports.notifications import RaiseIncident
from app.db.models import (
    AIAgent,
    FailureEvent,
    HealthState,
    Job,
    JobRetryState,
    JobState,
    Task,
    TaskState,
    WorkerRun,
)
from app.domain.notifications import NotificationSeverity
from app.domain.orchestration import (
    CircuitSnapshot,
    CircuitState,
    FailureScope,
    RecoveryAction,
    classify_failure_details,
    failure_resource_id,
    record_failure,
)
from app.infrastructure.external_task_sync import sync_external_task_state
from app.infrastructure.persistence.job_operations import record_event, release_workspace_lease
from app.infrastructure.persistence.notifications import SqlAlchemyNotificationStore


class SqlAlchemyFailedCompletionUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._command: FailedJobCommand | None = None

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: types.TracebackType | None,
    ) -> None:
        if self._session is not None:
            if exc is not None:
                await self._session.rollback()
            await self._session.close()

    def _active_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Failed-completion unit of work is not active")
        return self._session

    async def begin(self, command: FailedJobCommand) -> FailedJobContext | None:
        session = self._active_session()
        job = await session.get(Job, command.job_id, with_for_update=True)
        if job is None or job.lease_token != command.lease_token:
            return None
        task = await session.get(Task, job.task_id, with_for_update=True)
        if task is None:
            raise RuntimeError(f"Task {job.task_id} disappeared while its job was running")
        job.state = JobState(command.terminal_state)
        job.result = None
        job.failure_reason = command.failure
        job.finished_at = command.finished_at
        job.lease_expires_at = None
        await release_workspace_lease(session, job)
        self._command = command
        classification = classify_failure_details(
            code=command.terminal_state,
            outcome=command.failure,
        )
        worker_run = await session.scalar(
            select(WorkerRun)
            .where(WorkerRun.job_id == job.id)
            .order_by(WorkerRun.created_at.desc())
            .limit(1)
        )
        provider = worker_run.provider if worker_run else None
        model = worker_run.model if worker_run else None
        if provider is None and job.agent_id and classification.resource_type == "PROVIDER":
            agent = await session.get(AIAgent, job.agent_id)
            provider = agent.provider if agent else None
        resource_id = failure_resource_id(classification, provider=provider, model=model)
        fingerprint_source = f"{classification.failure_class.value}:{resource_id or job.id}"
        fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()[:32]
        retry_state = await session.get(JobRetryState, job.id, with_for_update=True)
        if retry_state is None:
            retry_state = JobRetryState(job_id=job.id)
            session.add(retry_state)
        self._increment_retry_counter(retry_state, classification.scope)
        retry_state.last_failure_fingerprint = fingerprint
        session.add(
            FailureEvent(
                task_id=task.id,
                job_id=job.id,
                resource_type=classification.resource_type,
                resource_id=resource_id,
                failure_class=classification.failure_class.value,
                fingerprint=fingerprint,
                error_code=command.terminal_state,
                safe_message=classification.safe_message,
                technical_details_json={"terminal_state": command.terminal_state},
                retryable=classification.retryable,
            )
        )
        circuit_open = False
        if classification.resource_type and resource_id:
            health = await self._load_health(classification.resource_type, resource_id)
            updated = record_failure(
                CircuitSnapshot(
                    CircuitState(health.circuit_state),
                    health.consecutive_failures,
                    health.next_probe_at,
                ),
                now=command.finished_at,
            )
            health.status = (
                "AUTH_ERROR"
                if classification.action is RecoveryAction.WAIT_CONFIGURATION
                else "UNAVAILABLE"
                if updated.state is CircuitState.OPEN
                else "DEGRADED"
            )
            health.circuit_state = updated.state.value
            health.consecutive_failures = updated.consecutive_failures
            health.last_failure_at = command.finished_at
            health.next_probe_at = updated.next_probe_at
            health.last_error_class = classification.failure_class.value
            health.failure_fingerprint = fingerprint
            health.probe_job_id = None
            circuit_open = updated.state is CircuitState.OPEN
        return FailedJobContext(
            job.id,
            task.id,
            job.attempt,
            task.manual_takeover,
            classification.failure_class.value,
            classification.action.value,
            classification.severity,
            classification.safe_message,
            fingerprint,
            classification.resource_type,
            resource_id,
            circuit_open,
        )

    async def _load_health(self, resource_type: str, resource_id: str) -> HealthState:
        session = self._active_session()
        health = await session.scalar(
            select(HealthState)
            .where(
                HealthState.resource_type == resource_type,
                HealthState.resource_id == resource_id,
            )
            .with_for_update()
        )
        if health is None:
            health = HealthState(resource_type=resource_type, resource_id=resource_id)
            session.add(health)
        return health

    @staticmethod
    def _increment_retry_counter(retry_state: JobRetryState, scope: FailureScope) -> None:
        if scope is FailureScope.PROVIDER:
            retry_state.provider_retry_count += 1
        elif scope is FailureScope.INTEGRATION:
            retry_state.integration_retry_count += 1
        elif scope is FailureScope.WORKER_RUNTIME:
            retry_state.worker_retry_count += 1
        elif scope is FailureScope.REQUEST:
            retry_state.protocol_retry_count += 1
        elif scope is FailureScope.TASK:
            retry_state.engineering_retry_count += 1

    async def schedule_retry(
        self, context: FailedJobContext, delay_seconds: int, max_attempts: int
    ) -> None:
        session = self._active_session()
        job = await session.get(Job, context.job_id)
        if job is None or self._command is None:
            raise RuntimeError("Failed job disappeared before retry scheduling")
        job.state = JobState.RETRY_WAIT
        job.worker_id = None
        job.lease_token = None
        job.retry_not_before = self._command.finished_at + timedelta(seconds=delay_seconds)
        await record_event(
            session,
            context.task_id,
            "JOB_RETRY_SCHEDULED",
            {
                "job_id": str(context.job_id),
                "attempt": context.attempt,
                "max_attempts": max_attempts,
                "delay_seconds": delay_seconds,
                "reason": self._command.failure,
                "failure_class": context.failure_class,
            },
        )

    async def exhaust(self, context: FailedJobContext) -> None:
        session = self._active_session()
        task = await session.get(Task, context.task_id)
        if task is None or self._command is None:
            raise RuntimeError("Task disappeared before failure escalation")
        task.state = TaskState.NEEDS_HUMAN
        await record_event(
            session,
            context.task_id,
            "JOB_FAILED",
            {
                "job_id": str(context.job_id),
                "attempts": context.attempt,
                "reason": self._command.failure,
                "failure_class": context.failure_class,
            },
        )

    async def wait(self, context: FailedJobContext, state: str) -> None:
        session = self._active_session()
        job = await session.get(Job, context.job_id)
        task = await session.get(Task, context.task_id)
        if job is None or task is None:
            raise RuntimeError("Job or Task disappeared before wait transition")
        job.state = JobState(state)
        job.worker_id = None
        job.lease_token = None
        job.retry_not_before = None
        if state in {"WAITING_CONFIGURATION", "WAITING_HUMAN"}:
            task.state = TaskState.NEEDS_HUMAN
        await record_event(
            session,
            context.task_id,
            f"JOB_{state}",
            {
                "job_id": str(context.job_id),
                "failure_class": context.failure_class,
                "resource_type": context.resource_type,
                "resource_id": context.resource_id,
            },
        )

    async def raise_incident(self, context: FailedJobContext) -> None:
        severity = NotificationSeverity(context.severity)
        await SqlAlchemyNotificationStore(self._active_session()).raise_incident(
            RaiseIncident(
                fingerprint=context.fingerprint,
                type=context.failure_class,
                severity=severity,
                title=context.failure_class.replace("_", " ").title(),
                summary=context.safe_message,
                task_id=context.task_id,
                job_id=context.job_id,
                action_target=f"/tasks/{context.task_id}",
                metadata={
                    "resource_type": context.resource_type or "JOB",
                    "resource_id": context.resource_id or str(context.job_id),
                },
            ),
            commit=False,
        )

    async def finish_during_takeover(self, context: FailedJobContext) -> None:
        if self._command is None:
            raise RuntimeError("Failure command is unavailable")
        await record_event(
            self._active_session(),
            context.task_id,
            "JOB_FINISHED_DURING_TAKEOVER",
            {"job_id": str(context.job_id), "state": self._command.terminal_state},
        )

    async def commit(self) -> None:
        await self._active_session().commit()

    async def synchronize_tracker(self, task_id: uuid.UUID) -> None:
        session = self._active_session()
        task = await session.get(Task, task_id)
        if task is not None:
            await sync_external_task_state(session, task)


class SqlAlchemyFailedCompletionUnitOfWorkFactory:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def __call__(self) -> SqlAlchemyFailedCompletionUnitOfWork:
        return SqlAlchemyFailedCompletionUnitOfWork(self._session_factory)
