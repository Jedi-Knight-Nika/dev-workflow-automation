"""Apply a decision atomically, then deliver its message through a durable outbox."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.domain.envelope import AgentEnvelope
from app.agent_runtime.infrastructure.agent_codec import canonical
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.agent_runtime.infrastructure.reservations import consumed_cost
from app.coordinator.application.ports import ConversationGateway
from app.coordinator.domain.protocol import Directive, validate_effect
from app.coordinator.infrastructure.authority import authorized, coordination_mode
from app.coordinator.infrastructure.models import (
    CoordinatorAction,
    CoordinatorEvent,
    CoordinatorRun,
    HumanRequest,
)
from app.coordinator.infrastructure.queries import latest_human_request, requeue_run_events
from app.coordinator.infrastructure.schemas import parse_decision
from app.delivery.infrastructure.status_sync import enqueue_status
from app.engineering.domain.causality import TransitionCause
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.infrastructure.controls import control_task
from app.engineering.infrastructure.job_queue import request_execution
from app.engineering.infrastructure.lifecycle import record_transition
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.models import ReviewCycle
from app.engineering.infrastructure.requirements import ACCEPTED_REQUIREMENT, current_requirement
from app.engineering.infrastructure.task_models import Task, TaskEvent
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.team_models import Team


class NewInformation(ValueError):
    """Retain the complete event batch for a fresh decision."""


class EngineeringBusy(ValueError):
    """An in-flight paid generation owns the workspace until its receipt settles."""


DELIVERY_CHECK_TIMEOUT_SECONDS = 45


class ActionExecutor:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], conversations: ConversationGateway
    ) -> None:
        self.sessions, self.conversations = sessions, conversations

    async def _apply(self, session: AsyncSession, action: CoordinatorAction, task: Task) -> None:
        run = await session.get(CoordinatorRun, action.run_id)
        event = await session.get(CoordinatorEvent, UUID(str(action.arguments["event_id"])))
        if not run or not event or not await authorized(session, task, event):
            raise ValueError("Coordinator event authority was revoked")
        team = await session.get(Team, task.team_id) if task.team_id else None
        if (
            not team
            or not team.enabled
            or team.execution_paused
            or team.archived_at
            or task.archived_at
        ):
            raise ValueError("Task or Team is suspended")
        source_events = list(
            await session.scalars(select(CoordinatorEvent).where(CoordinatorEvent.run_id == run.id))
        )
        for source_event in source_events:
            source_provider = str(source_event.context.get("reply_provider", source_event.provider))
            if coordination_mode(source_provider) != "active" or not await authorized(
                session, task, source_event
            ):
                raise ValueError("Authority changed for a coalesced event")
        decision = parse_decision(action.arguments["decision"])
        message = "" if decision.action == Directive.WAIT else decision.message
        provider = str(event.context.get("reply_provider", event.provider))
        if coordination_mode(provider) != "active":
            raise ValueError("Active coordination was disabled for this provider")
        if any(
            source.provider == "github"
            and source.context.get("head_sha")
            and source.context["head_sha"] != task.current_revision
            for source in source_events
        ) and decision.action not in {Directive.WAIT, Directive.REPLY}:
            raise ValueError("Feedback refers to an older PR revision")
        human = await session.scalar(latest_human_request(task).with_for_update())
        validate_effect(
            decision,
            status=task.status,
            manual_takeover=task.manual_takeover,
            expected_revision=run.lifecycle_revision,
            current_revision=task.lifecycle_version,
            expected_requirement=run.requirement_revision,
            current_requirement=task.requirement_version,
            human_continuation=bool(
                human
                and human.status == "ANSWERED"
                and any(
                    source.kind == "HUMAN_RESPONSE"
                    and source.context.get("human_request_id") == str(human.id)
                    for source in source_events
                )
            ),
            engineering_event=event.provider == "engineering",
        )
        newer = await session.scalar(
            select(CoordinatorEvent.id)
            .where(
                CoordinatorEvent.task_id == task.id,
                CoordinatorEvent.created_at > run.created_at,
                CoordinatorEvent.status == "QUEUED",
            )
            .limit(1)
        )
        if newer:
            raise NewInformation("New information arrived; a newer decision is required")
        if any(e.context.get("body_truncated") for e in source_events) and decision.action in {
            Directive.IMPLEMENT,
            Directive.REPAIR,
        }:
            raise ValueError("Feedback exceeds the context bound; request a concise clarification")
        if decision.action == Directive.REQUEST_REVIEW:
            if coordination_mode("github") != "active":
                raise ValueError("Active GitHub coordination is required to request review")
            policy = await read_policy(session, team.id)
            if (
                not task.pull_request_number
                or not task.current_revision
                or not policy.authorized_reviewer_ids
            ):
                raise ValueError("Review requests require a published PR and explicit reviewer IDs")
        if decision.action == Directive.REQUEST_VALIDATION:
            from app.engineering.infrastructure.validation_requests import request_validation

            policy = await read_policy(session, team.id)
            repository = (
                await session.get(Repository, task.repository_id) if task.repository_id else None
            )
            if (
                not repository
                or not repository.enabled
                or repository.archived_at
                or not policy.enrollment_enabled
                or repository.id not in policy.repository_ids
            ):
                raise ValueError("Repository validation scope was revoked")
            await request_validation(
                session, task, actor="coordinator", cause=TransitionCause(action_id=action.id)
            )
        if decision.action == Directive.SYNC_STATUS:
            await enqueue_status(session, task.id, task.lifecycle_version, task.status, task.stage)
        actor = "coordinator"
        cause = TransitionCause(action_id=action.id)
        if decision.action == Directive.ASK_HUMAN:
            if human:
                human.status = "CANCELLED"
            await control_task(
                session,
                task,
                Action.BLOCK,
                actor=actor,
                wait_reason=WaitReason.MISSING_REQUIREMENT,
                cause=cause,
            )
            session.add(
                HumanRequest(
                    task_id=task.id,
                    run_id=run.id,
                    question=decision.message,
                    reason=decision.reason,
                    choices=decision.choices,
                    requirement_revision=task.requirement_version,
                    lifecycle_revision=task.lifecycle_version,
                )
            )
            session.add(
                TaskEvent(
                    task_id=task.id,
                    source=actor,
                    event_type="HUMAN_INPUT_REQUIRED",
                    payload={"run_id": str(run.id)},
                )
            )
        elif decision.action in {Directive.IMPLEMENT, Directive.REPAIR}:
            policy = await read_policy(session, team.id)
            repository = (
                await session.get(Repository, task.repository_id) if task.repository_id else None
            )
            if repository and (
                not repository.enabled
                or repository.archived_at
                or not policy.enrollment_enabled
                or repository.id not in policy.repository_ids
            ):
                raise ValueError("Repository or Team execution scope was revoked")
            # Do not cancel a paid generation only to discover that its usage is unknown.
            if await session.scalar(
                select(AIRun.id).where(AIRun.task_id == task.id, AIRun.status == "RUNNING").limit(1)
            ):
                raise EngineeringBusy("Waiting for the current Developer generation to settle")
            if await consumed_cost(session, task.id) is None:
                raise ValueError(
                    "Reconcile active or unknown AI usage before changing engineering work"
                )
            native = await session.scalar(
                select(DeveloperSession)
                .where(DeveloperSession.task_id == task.id)
                .order_by(DeveloperSession.generation.desc())
                .limit(1)
                .with_for_update()
            )
            amendment = {
                "request": decision.engineering_request,
                "invariants": list(decision.checkpoint.invariants),
            }
            await current_requirement(session, task, addition=amendment)
            if native:
                await control_task(session, task, Action.PAUSE, actor=actor, cause=cause)
                await record_transition(
                    session,
                    task.id,
                    Action.REVISE_REQUIREMENT,
                    expected_version=task.lifecycle_version,
                    actor=actor,
                    cause=cause,
                )
                native.checkpoint = {
                    **native.checkpoint,
                    "next_feedback": decision.engineering_request,
                    "coordinator_guidance": canonical(
                        AgentEnvelope(
                            1,
                            "repair" if decision.action == Directive.REPAIR else "work",
                            task.id,
                            task.requirement_version,
                            task.current_revision,
                            {
                                "request": decision.engineering_request,
                                "invariants": list(decision.checkpoint.invariants),
                            },
                            (str(run.id),),
                        )
                    ),
                }
                await control_task(session, task, Action.RESUME, actor=actor, cause=cause)
            else:
                task.requirement_version += 1
                await request_execution(session, task, actor=actor, cause=cause)
            session.add(
                TaskEvent(
                    task_id=task.id,
                    source=actor,
                    event_type=ACCEPTED_REQUIREMENT,
                    payload={
                        **amendment,
                        "requirement_revision": task.requirement_version,
                        "action_id": str(action.id),
                    },
                )
            )
        elif decision.action in {Directive.PAUSE, Directive.CANCEL}:
            await control_task(
                session, task, Action(decision.action.value), actor=actor, cause=cause
            )
        if event.context.get("review_cycle_id"):
            cycle = await session.get(
                ReviewCycle, UUID(str(event.context["review_cycle_id"])), with_for_update=True
            )
            if cycle:
                cycle.decision = (
                    "FEEDBACK_APPLIED"
                    if decision.action == Directive.REPAIR
                    else "IGNORED"
                    if decision.action in {Directive.REPLY, Directive.WAIT}
                    else "NEEDS_CLASSIFICATION"
                )
        if message:
            session.add(
                TaskMessage(
                    task_id=task.id,
                    author_type="COORDINATOR",
                    author_name="Coordinator",
                    author_role="COORDINATOR",
                    kind="QUESTION" if decision.action == Directive.ASK_HUMAN else "UPDATE",
                    body=message,
                    context={"action_id": str(action.id), "provider": event.provider},
                )
            )
        action.arguments = {
            **action.arguments,
            "provider": event.context.get("reply_provider", event.provider),
            "message": message,
            "requirement_revision": task.requirement_version,
            "lifecycle_revision": task.lifecycle_version,
        }
        action.status = (
            "DELIVERY_PENDING"
            if message or decision.action == Directive.REQUEST_REVIEW
            else "EXECUTED"
        )
        run.status = "COMPLETED"
        session.add(
            TaskEvent(
                task_id=task.id,
                source=actor,
                event_type="ACTION_EXECUTED",
                payload={"action_id": str(action.id), "action": decision.action},
            )
        )

    async def execute_one(self) -> bool:
        async with self.sessions.begin() as session:
            row = await session.scalar(
                select(CoordinatorAction)
                .where(
                    or_(
                        CoordinatorAction.status == "PENDING",
                        (CoordinatorAction.status == "WAITING_ENGINEER")
                        & or_(
                            ~select(AIRun.id)
                            .where(
                                AIRun.task_id == CoordinatorAction.task_id,
                                AIRun.status == "RUNNING",
                            )
                            .exists(),
                            select(CoordinatorEvent.id)
                            .where(
                                CoordinatorEvent.task_id == CoordinatorAction.task_id,
                                CoordinatorEvent.status == "QUEUED",
                                CoordinatorEvent.created_at > CoordinatorAction.created_at,
                            )
                            .exists(),
                        ),
                    )
                )
                .order_by(CoordinatorAction.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not row:
                return False
            task = await session.get(Task, row.task_id, with_for_update=True)
            run = await session.get(CoordinatorRun, row.run_id)
            if (
                task
                and run
                and (task.lifecycle_version, task.requirement_version)
                != (run.lifecycle_revision, run.requirement_revision)
            ):
                # Engineering made real progress while this intent waited. Reconsider
                # the retained human event with that new evidence; no effect is replayed.
                row.status, run.status = "SUPERSEDED", "SUPERSEDED"
                await requeue_run_events(session, run.id)
                return True
            try:
                async with session.begin_nested():
                    if not task:
                        raise ValueError("Task no longer exists")
                    await self._apply(session, row, task)
            except NewInformation as exc:
                await session.refresh(row)
                row.status, row.error = "SUPERSEDED", str(exc)
                run = await session.get(CoordinatorRun, row.run_id)
                assert run
                run.status = "SUPERSEDED"
                await requeue_run_events(session, run.id)
            except EngineeringBusy as exc:
                await session.refresh(row)
                row.status, row.error = "WAITING_ENGINEER", str(exc)
            except ValueError as exc:
                await session.refresh(row)
                row.status, row.error = "REJECTED", str(exc)[:500]
                run = await session.get(CoordinatorRun, row.run_id)
                if run:
                    run.status = "REJECTED"
        return True

    async def deliver_one(self) -> bool:
        async with self.sessions.begin() as session:
            action = await session.scalar(
                select(CoordinatorAction)
                .where(CoordinatorAction.status == "DELIVERY_PENDING")
                .order_by(CoordinatorAction.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not action:
                return False
            task = await session.get(Task, action.task_id)
            event = await session.get(CoordinatorEvent, UUID(str(action.arguments["event_id"])))
            team = await session.get(Team, task.team_id) if task and task.team_id else None
            if (
                not task
                or not event
                or not team
                or not team.enabled
                or team.execution_paused
                or team.archived_at
                or task.archived_at
                or task.manual_takeover
                or coordination_mode(str(action.arguments["provider"])) != "active"
                or (task.requirement_version, task.lifecycle_version)
                != (
                    action.arguments["requirement_revision"],
                    action.arguments["lifecycle_revision"],
                )
                or not await authorized(session, task, event)
            ):
                action.status, action.error = (
                    "REJECTED",
                    "Task changed or reply authority was revoked",
                )
                return True
            action.status, action.attempted_at = "SENDING", datetime.now(UTC)
            kind = action.kind
            if kind == "REQUEST_REVIEW" and coordination_mode("github") != "active":
                action.status, action.error = "REJECTED", "GitHub coordination was disabled"
                return True
            identifier, task_id, provider, message = (
                action.id,
                action.task_id,
                str(action.arguments["provider"]),
                str(action.arguments["message"]),
            )
        try:
            async with asyncio.timeout(45):
                reference = (
                    await self.conversations.request_review(task_id, identifier)
                    if kind == "REQUEST_REVIEW"
                    else await self.conversations.reply(task_id, provider, message, identifier)
                )
        except Exception as exc:  # noqa: BLE001 -- persist a sanitized failure at the worker/effect boundary
            async with self.sessions.begin() as session:
                row = await session.get(CoordinatorAction, identifier, with_for_update=True)
                assert row
                if row.status == "EXECUTED":
                    return True  # An authenticated echo already confirmed the effect.
                row.arguments = {**row.arguments, "reconcile_requested": kind != "REQUEST_REVIEW"}
                row.status, row.error = (
                    "UNKNOWN",
                    f"Delivery not confirmed ({type(exc).__name__}); inspect the original conversation before retrying",
                )
        else:
            async with self.sessions.begin() as session:
                row = await session.get(CoordinatorAction, identifier, with_for_update=True)
                assert row
                row.status, row.provider_effect_ref, row.error = "EXECUTED", reference, None
        return True

    async def reconcile_one(self) -> bool:
        async with self.sessions.begin() as session:
            action = await session.scalar(
                select(CoordinatorAction)
                .where(
                    CoordinatorAction.status == "UNKNOWN",
                    CoordinatorAction.arguments["reconcile_requested"].as_boolean().is_(True),
                )
                .order_by(CoordinatorAction.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not action or not action.attempted_at:
                return False
            action.status = "RECONCILING"
            action.arguments = {
                **action.arguments,
                "reconcile_requested": False,
                "reconcile_started_at": datetime.now(UTC).isoformat(),
            }
            identifier, task_id, attempted, kind, arguments = (
                action.id,
                action.task_id,
                action.attempted_at,
                action.kind,
                dict(action.arguments),
            )
        error = "Delivery still uncertain; bounded provider history did not identify a unique matching message. No resend occurred."
        reference = None
        try:
            async with asyncio.timeout(DELIVERY_CHECK_TIMEOUT_SECONDS):
                reference = await self.conversations.reconcile(
                    task_id,
                    str(arguments["provider"]),
                    str(arguments["message"]),
                    identifier,
                    attempted,
                    kind,
                )
        except Exception as exc:  # noqa: BLE001 -- sanitize provider errors at the effect boundary
            error = f"Delivery verification unavailable ({type(exc).__name__}); no resend occurred"
        async with self.sessions.begin() as session:
            row = await session.get(CoordinatorAction, identifier, with_for_update=True)
            assert row
            if row.status == "EXECUTED":
                return True
            row.status = "EXECUTED" if reference else "UNKNOWN"
            row.provider_effect_ref, row.error = reference, None if reference else error
            session.add(
                TaskEvent(
                    task_id=task_id,
                    source="coordinator",
                    event_type="DELIVERY_RECONCILED",
                    payload={"action_id": str(identifier), "status": row.status},
                )
            )
        return True

    async def recover(self) -> None:
        async with self.sessions.begin() as session:
            rows = await session.scalars(
                select(CoordinatorAction)
                .where(
                    CoordinatorAction.status == "SENDING",
                    CoordinatorAction.attempted_at < datetime.now(UTC) - timedelta(minutes=2),
                )
                .with_for_update(skip_locked=True)
            )
            for row in rows:
                row.arguments = {
                    **row.arguments,
                    "reconcile_requested": row.kind != "REQUEST_REVIEW",
                }
                row.status, row.error = (
                    "UNKNOWN",
                    "Interrupted delivery; inspect provider conversation before retrying",
                )
            checking = await session.scalars(
                select(CoordinatorAction)
                .where(CoordinatorAction.status == "RECONCILING")
                .with_for_update(skip_locked=True)
            )
            for row in checking:
                started = datetime.fromisoformat(str(row.arguments["reconcile_started_at"]))
                if started < datetime.now(UTC) - timedelta(minutes=2):
                    row.status, row.error = (
                        "UNKNOWN",
                        "Delivery verification was interrupted; check again",
                    )
