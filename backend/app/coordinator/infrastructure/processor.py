"""Coalesced, task-serialized decisions. No database lock spans model inference."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.coordinator.application.ports import ConversationGateway, DecisionModel
from app.coordinator.infrastructure.authority import authorized
from app.coordinator.infrastructure.models import (
    CoordinatorAction,
    CoordinatorEvent,
    CoordinatorRun,
)
from app.coordinator.infrastructure.queries import latest_human_request, requeue_run_events
from app.coordinator.infrastructure.schemas import decision_payload
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.requirements import current_requirement
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.platform.configuration.settings import Settings
from app.teams.infrastructure.team_models import Team


class SituationChanged(ValueError):
    """Completed engineering changes require fresh evidence for retained feedback."""


class CoordinatorProcessor:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        model: DecisionModel,
        conversations: ConversationGateway,
    ) -> None:
        self.sessions, self.settings, self.model, self.conversations = (
            sessions,
            settings,
            model,
            conversations,
        )

    async def claim(self) -> tuple[UUID, UUID, str, dict[str, Any]] | None:
        async with self.sessions.begin() as session:
            event = await session.scalar(
                select(CoordinatorEvent)
                .where(
                    CoordinatorEvent.status == "QUEUED",
                    CoordinatorEvent.available_at <= datetime.now(UTC),
                    ~select(CoordinatorRun.id)
                    .where(
                        CoordinatorRun.task_id == CoordinatorEvent.task_id,
                        CoordinatorRun.status.in_(["CLAIMED", "READY"]),
                    )
                    .exists(),
                )
                .order_by(CoordinatorEvent.available_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not event:
                return None
            task = await session.scalar(
                select(Task).where(Task.id == event.task_id).with_for_update(skip_locked=True)
            )
            if not task:
                return None
            if await session.scalar(
                select(CoordinatorRun.id).where(
                    CoordinatorRun.task_id == task.id,
                    CoordinatorRun.status.in_(["CLAIMED", "READY"]),
                )
            ):
                return None
            team = await session.get(Team, task.team_id) if task.team_id else None
            if (
                not team
                or not team.enabled
                or team.execution_paused
                or team.archived_at
                or task.archived_at
                or task.manual_takeover
            ):
                event.status = "SUSPENDED"
                return None
            batch = list(
                await session.scalars(
                    select(CoordinatorEvent)
                    .where(
                        CoordinatorEvent.task_id == task.id,
                        CoordinatorEvent.status == "QUEUED",
                        CoordinatorEvent.created_at <= datetime.now(UTC),
                    )
                    .order_by(CoordinatorEvent.created_at)
                    .limit(5)
                    .with_for_update(skip_locked=True)
                )
            )
            admitted = []
            for item in batch:
                target_provider = str(item.context.get("reply_provider", item.provider))
                if (
                    self.settings.coordinator_mode == "off"
                    or target_provider not in self.settings.coordinator_providers
                ):
                    item.status = "SUSPENDED"
                    continue
                if await authorized(session, task, item):
                    admitted.append(item)
                else:
                    item.status = "UNAUTHORIZED"
            if not admitted:
                return None
            latest = next(
                (item for item in reversed(admitted) if item.provider != "engineering"),
                admitted[-1],
            )
            messages = list(
                await session.scalars(
                    select(TaskMessage)
                    .where(TaskMessage.task_id == task.id)
                    .order_by(TaskMessage.id.desc())
                    .limit(10)
                )
            )
            previous = await session.scalar(
                select(CoordinatorRun)
                .where(
                    CoordinatorRun.task_id == task.id,
                    CoordinatorRun.status == "COMPLETED",
                )
                .order_by(CoordinatorRun.created_at.desc())
                .limit(1)
            )
            human = await session.scalar(latest_human_request(task))
            checks = list(
                await session.scalars(
                    select(ValidationRun)
                    .where(
                        ValidationRun.task_id == task.id,
                        ValidationRun.requirement_version == task.requirement_version,
                        ValidationRun.head_sha == task.current_revision,
                    )
                    .order_by(ValidationRun.started_at.desc())
                    .limit(3)
                )
            )
            try:
                requirement = await current_requirement(session, task)
            except ValueError as exc:
                failed = CoordinatorRun(
                    task_id=task.id,
                    mode=self.settings.coordinator_mode,
                    status="FAILED",
                    requirement_revision=task.requirement_version,
                    lifecycle_revision=task.lifecycle_version,
                    error=str(exc)[:500],
                    finished_at=datetime.now(UTC),
                    evidence={"event_id": str(latest.id)},
                )
                session.add(failed)
                await session.flush()
                for item in admitted:
                    item.status, item.run_id = "FAILED", failed.id
                return None
            packet = {
                "trigger_provider": latest.provider,
                "original_requirement": requirement,
                "status": task.status,
                "stage": task.stage,
                "current_sha": task.current_revision,
                "requirement_revision": task.requirement_version,
                "events": [
                    {
                        "provider": e.provider,
                        "kind": e.kind,
                        "body": str(e.context.get("body", "")),
                        "bounded_excerpt": bool(e.context.get("body_truncated")),
                    }
                    for e in admitted[-5:]
                ],
                "recent_messages": [
                    {"author": m.author_name, "body": m.body[:800]} for m in reversed(messages)
                ],
                "checkpoint": previous.decision.get("checkpoint")
                if previous and previous.decision
                else None,
                "human_request": {
                    "question": human.question,
                    "answer": human.answer,
                    "status": human.status,
                }
                if human
                else None,
                "validation": [{"status": c.status, "sha": c.head_sha} for c in checks],
            }
            run = CoordinatorRun(
                task_id=task.id,
                mode=self.settings.coordinator_mode,
                requirement_revision=task.requirement_version,
                lifecycle_revision=task.lifecycle_version,
                evidence={
                    "event_id": str(latest.id),
                    "provider": latest.provider,
                    "kind": latest.kind,
                    "packet": packet,
                },
            )
            session.add(run)
            await session.flush()
            for item in admitted:
                item.status, item.run_id = "CLAIMED", run.id
            session.add(
                TaskEvent(
                    task_id=task.id,
                    source="coordinator",
                    event_type="COORDINATOR_STARTED",
                    payload={"run_id": str(run.id), "events": len(admitted), "mode": run.mode},
                )
            )
            return (
                run.id,
                task.id,
                str(latest.context.get("reply_provider", latest.provider)),
                packet,
            )

    async def _watch(self, run_id: UUID) -> None:
        while True:
            await asyncio.sleep(1)
            async with self.sessions() as session:
                run = await session.get(CoordinatorRun, run_id)
                task = await session.get(Task, run.task_id) if run else None
                team = await session.get(Team, task.team_id) if task and task.team_id else None
                if (
                    not run
                    or run.status != "CLAIMED"
                    or not task
                    or not team
                    or not team.enabled
                    or team.execution_paused
                    or team.archived_at
                    or task.manual_takeover
                    or task.archived_at
                ):
                    raise ValueError("Coordinator authority changed during inference")
                if (task.lifecycle_version, task.requirement_version) != (
                    run.lifecycle_revision,
                    run.requirement_revision,
                ):
                    raise SituationChanged("Task advanced during inference")

    async def process_one(self) -> bool:
        claimed = await self.claim()
        if not claimed:
            return False
        run_id, task_id, provider, packet = claimed

        async def decide() -> None:
            decision = await self.model.decide(run_id, packet, 0)
            if decision.read_tools:
                evidence: dict[str, Any] = {}
                for tool in dict.fromkeys(decision.read_tools):
                    try:
                        evidence[tool] = await self.conversations.read(task_id, provider, tool)
                    except (ValueError, LookupError, TimeoutError, OSError, httpx.HTTPError) as exc:
                        evidence[tool] = {"unavailable": type(exc).__name__}
                packet["requested_evidence"] = evidence
                decision = await self.model.decide(run_id, packet, 1)
                if decision.read_tools:
                    raise ValueError("Coordinator exhausted its context expansion")
            async with self.sessions.begin() as session:
                run = await session.get(CoordinatorRun, run_id, with_for_update=True)
                assert run
                run.decision = decision_payload(decision)
                run.status = "SHADOW" if run.mode == "shadow" else "READY"
                run.finished_at = datetime.now(UTC)
                run.evidence = {**run.evidence, "packet": packet}
                if run.mode == "active":
                    session.add(
                        CoordinatorAction(
                            run_id=run.id,
                            task_id=task_id,
                            kind=decision.action,
                            arguments={
                                "decision": run.decision,
                                "event_id": run.evidence["event_id"],
                            },
                        )
                    )
                await session.execute(
                    update(CoordinatorEvent)
                    .where(CoordinatorEvent.run_id == run_id)
                    .values(status="PROCESSED")
                )
                session.add(
                    TaskEvent(
                        task_id=task_id,
                        source="coordinator",
                        event_type="COORDINATOR_DECIDED",
                        payload={
                            "run_id": str(run.id),
                            "action": decision.action,
                            "mode": run.mode,
                        },
                    )
                )

        operation, watcher = asyncio.create_task(decide()), asyncio.create_task(self._watch(run_id))
        try:
            async with asyncio.timeout(150):
                finished, _ = await asyncio.wait(
                    {operation, watcher}, return_when=asyncio.FIRST_COMPLETED
                )
                if operation in finished:
                    operation.result()
                else:
                    watcher.result()
        except BaseException as exc:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            async with self.sessions.begin() as session:
                run = await session.get(CoordinatorRun, run_id, with_for_update=True)
                if run and run.status == "CLAIMED":
                    run.status, run.error, run.finished_at = (
                        "SUPERSEDED" if isinstance(exc, SituationChanged) else "FAILED",
                        str(exc)[:500] if type(exc) is ValueError else type(exc).__name__,
                        datetime.now(UTC),
                    )
                    if isinstance(exc, SituationChanged):
                        await requeue_run_events(session, run_id)
                    else:
                        await session.execute(
                            update(CoordinatorEvent)
                            .where(CoordinatorEvent.run_id == run_id)
                            .values(status="FAILED")
                        )
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            operation.cancel()
            watcher.cancel()
            await asyncio.gather(operation, watcher, return_exceptions=True)
        return True

    async def recover(self) -> None:
        # Stale paid attempts remain stopped, with unknown usage visible in AIRun.
        from app.agent_runtime.infrastructure.models import AIRun

        async with self.sessions.begin() as session:
            rows = await session.scalars(
                select(CoordinatorRun)
                .where(
                    CoordinatorRun.status == "CLAIMED",
                    CoordinatorRun.created_at < datetime.now(UTC) - timedelta(minutes=5),
                )
                .with_for_update(skip_locked=True)
            )
            for run in rows:
                run.status, run.error = (
                    "FAILED",
                    "Interrupted decision; inspect usage before retrying",
                )
                await session.execute(
                    update(CoordinatorEvent)
                    .where(CoordinatorEvent.run_id == run.id)
                    .values(status="FAILED")
                )
                await session.execute(
                    update(AIRun)
                    .where(
                        AIRun.native_turn_id.like(f"coordinator:{run.id}:%"),
                        AIRun.status == "RUNNING",
                    )
                    .values(
                        status="INTERRUPTED",
                        failure_code="COORDINATOR_INTERRUPTED",
                        finished_at=datetime.now(UTC),
                    )
                )
