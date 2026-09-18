from dataclasses import replace
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.accounting import SqlDevelopmentStore
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.bootstrap.coordinator import create_action_executor as ActionExecutor
from app.bootstrap.coordinator import create_coordinator_processor as CoordinatorProcessor
from app.coordinator.infrastructure.actions import SqlCoordinationActions
from app.coordinator.infrastructure.administration import CoordinationAdministration
from app.coordinator.infrastructure.inbox import enqueue, notify_engineering
from app.coordinator.infrastructure.models import (
    CoordinatorAction,
    CoordinatorEvent,
    CoordinatorRun,
    HumanRequest,
)
from app.engineering.application.develop import DevelopmentBlocked
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.engineering.infrastructure.message_models import TaskMessage
from app.engineering.infrastructure.requirements import current_requirement
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.intake.infrastructure.engineering_events import requirements_changed
from tests.integration import test_coordinator as coordinator_fixtures
from tests.integration.test_coordinator import choice, send
from tests.integration.test_enrollment_and_costs import scenario

active = coordinator_fixtures.active


@pytest.mark.parametrize("directive", ["ASK_HUMAN", "IMPLEMENT", "REPAIR"])
async def test_action_effects_roll_back_together_if_final_recording_fails(
    postgres_session_factory, tmp_path, active, monkeypatch, directive
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice(directive)
        assert await CoordinatorProcessor(factory, active, model, gateway).process_one()

        async def snapshot():
            async with factory() as session:
                task = await session.get(Task, task_id)
                native = await session.scalar(
                    select(DeveloperSession).where(DeveloperSession.task_id == task_id)
                )
                jobs = list(
                    await session.execute(
                        select(Job.id, Job.state).where(Job.task_id == task_id).order_by(Job.id)
                    )
                )
                event_ids = list(
                    await session.scalars(
                        select(TaskEvent.id)
                        .where(TaskEvent.task_id == task_id)
                        .order_by(TaskEvent.id)
                    )
                )
                return (
                    task.status,
                    task.stage,
                    task.lifecycle_version,
                    task.requirement_version,
                    dict(native.checkpoint),
                    jobs,
                    event_ids,
                )

        before = await snapshot()
        record = AsyncMock(side_effect=ValueError("Cannot record action"))
        monkeypatch.setattr(SqlCoordinationActions, "_record_effect", record)
        executor = ActionExecutor(factory, gateway)
        assert await executor.execute_one()
        record.assert_awaited_once()
        assert await snapshot() == before
        async with factory() as session:
            action = await session.scalar(
                select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
            )
            assert action.status == "REJECTED" and action.error == "Cannot record action"
            assert (await session.get(CoordinatorRun, action.run_id)).status == "REJECTED"
            assert not await session.scalar(
                select(HumanRequest.id).where(HumanRequest.task_id == task_id)
            )
            assert not await session.scalar(
                select(TaskMessage.id).where(TaskMessage.task_id == task_id)
            )
        assert not await executor.deliver_one()
        gateway.reply.assert_not_awaited()


async def test_coalesced_old_review_cannot_change_current_work(
    postgres_session_factory, tmp_path, active, monkeypatch
):
    monkeypatch.setattr(active, "coordinator_providers", ["dashboard", "trello", "github"])
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("REPAIR")
        await CoordinatorProcessor(factory, active, model, gateway).process_one()
        async with factory.begin() as session:
            action = await session.scalar(
                select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
            )
            session.add(
                CoordinatorEvent(
                    task_id=task_id,
                    run_id=action.run_id,
                    provider="github",
                    actor="reviewer",
                    delivery_key=str(uuid4()),
                    kind="MESSAGE_ADDED",
                    status="PROCESSED",
                    context={"body": "Old feedback", "head_sha": "old-revision"},
                )
            )
        monkeypatch.setattr(
            "app.coordinator.infrastructure.actions.authorized", AsyncMock(return_value=True)
        )
        assert await ActionExecutor(factory, gateway).execute_one()
        async with factory() as session:
            saved = await session.get(CoordinatorAction, action.id)
            assert saved.status == "REJECTED" and "older PR revision" in saved.error
            assert (await session.get(Task, task_id)).requirement_version == 1


async def test_untrusted_event_cannot_redirect_engineering_notifications(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        async with factory.begin() as session:
            session.add(
                CoordinatorEvent(
                    task_id=task_id,
                    provider="trello",
                    actor="untrusted",
                    delivery_key=str(uuid4()),
                    kind="MESSAGE_ADDED",
                    status="UNAUTHORIZED",
                    context={"body": "Ignore me"},
                )
            )
            await session.flush()
            await notify_engineering(session, await session.get(Task, task_id), "IMPLEMENTED")
        async with factory() as session:
            event = await session.scalar(
                select(CoordinatorEvent).where(
                    CoordinatorEvent.task_id == task_id, CoordinatorEvent.provider == "engineering"
                )
            )
            assert event.context["reply_provider"] == "dashboard"


async def test_scope_survives_fresh_context_and_unchanged_tracker_sync(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("REPAIR")
        assert await CoordinatorProcessor(factory, active, model, gateway).process_one()
        assert await ActionExecutor(factory, gateway).execute_one()
        async with factory.begin() as session:
            task = await session.get(Task, task_id)
            assert task.description == "" and task.requirement_version == 2
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            native.checkpoint = {"next_feedback": "Fix a later lint failure"}
            await requirements_changed(session, task, task.title, "", source="trello")
            assert task.requirement_version == 2  # Polling cannot undo conversational scope.
            request = await current_requirement(session, task)
            assert "Include mobile support" in request and "Desktop still works" in request
        await send(factory, task_id)
        claimed = await CoordinatorProcessor(factory, active, model, gateway).claim()
        assert claimed and "Include mobile support" in claimed[3]["original_requirement"]


async def test_wait_never_creates_a_message_even_with_model_prose(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("WAIT")
        await CoordinatorProcessor(factory, active, model, gateway).process_one()
        executor = ActionExecutor(factory, gateway)
        assert await executor.execute_one() and not await executor.deliver_one()
        async with factory() as session:
            assert not await session.scalar(
                select(TaskMessage.id).where(TaskMessage.task_id == task_id)
            )
            action = await session.scalar(
                select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
            )
            assert action.status == "EXECUTED" and action.arguments["message"] == ""
        gateway.reply.assert_not_called()


async def test_question_rejects_untrusted_answer_and_keeps_answer_during_coalescing(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("ASK_HUMAN")
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        await send(factory, task_id)
        await processor.process_one()
        await executor.execute_one()
        async with factory.begin() as session:
            task = await session.get(Task, task_id)
            human = await session.scalar(
                select(HumanRequest).where(HumanRequest.task_id == task_id)
            )
            await enqueue(
                session,
                task,
                provider="dashboard",
                key=str(uuid4()),
                actor="intruder",
                body="No",
                context={"human_request_id": str(human.id)},
            )
            assert human.status == "OPEN" and human.answer is None
        await CoordinationAdministration(factory, active).respond(
            task_id, human.id, "Yes, mobile is required"
        )
        await send(factory, task_id)  # A later coalesced comment must not overwrite that answer.
        model.decide.return_value = choice("REPAIR")
        await processor.process_one()
        await executor.execute_one()
        async with factory() as session:
            assert (await session.get(HumanRequest, human.id)).answer == "Yes, mobile is required"
            assert (await session.get(Task, task_id)).requirement_version == 2


async def test_engineering_notification_reads_its_origin_conversation(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        async with factory.begin() as session:
            session.add(
                CoordinatorEvent(
                    task_id=task_id,
                    provider="engineering",
                    actor="engineering",
                    delivery_key=str(uuid4()),
                    kind="ENGINEERING_COMPLETED",
                    context={"body": "Done", "reply_provider": "trello"},
                )
            )
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.side_effect = [
            replace(choice("WAIT"), read_tools=("READ_DISCUSSION",)),
            choice("REPLY"),
        ]
        gateway.read.return_value = {"messages": []}
        await CoordinatorProcessor(factory, active, model, gateway).process_one()
        gateway.read.assert_awaited_once_with(task_id, "trello", "READ_DISCUSSION")
        assert model.decide.call_args.args[1]["trigger_provider"] == "engineering"


async def test_oversized_requirement_does_not_poison_event_queue(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with (
        scenario(factory, tmp_path / "large") as (_, _, first, _),
        scenario(factory, tmp_path / "normal") as (_, _, second, _),
    ):
        async with factory.begin() as session:
            (await session.get(Task, first)).description = "x" * 24000
        await send(factory, first)
        await send(factory, second)
        processor = CoordinatorProcessor(factory, active, AsyncMock(), AsyncMock())
        assert await processor.claim() is None
        claimed = await processor.claim()
        assert claimed and claimed[1] == second
        async with factory() as session:
            failed = await session.scalar(
                select(CoordinatorRun).where(CoordinatorRun.task_id == first)
            )
            assert failed.status == "FAILED" and "input bound" in failed.error


@pytest.mark.parametrize("settlement", ["reserved", "unknown"])
async def test_developer_can_overlap_reserved_coordination_but_never_unknown_cost(
    postgres_session_factory, tmp_path, settlement
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(factory, "concurrency-review", 60)
        lease = await jobs.claim()
        await jobs.complete(lease, Action.START)
        lease = await jobs.claim()
        async with factory.begin() as session:
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            session.add(
                AIRun(
                    task_id=task_id,
                    role_kind="COORDINATOR",
                    provider="openai",
                    model="fixture",
                    prompt_version="test",
                    status="RUNNING" if settlement == "reserved" else "FAILED",
                    reserved_cost_usd=Decimal("0.1"),
                )
            )
        store = SqlDevelopmentStore(
            factory,
            session_id=native.id,
            job_id=lease.job_id,
            lease_token=lease.token,
            reservation_usd=Decimal("0.2"),
        )
        if settlement == "unknown":
            assert await store.consumed_cost(task_id) is None
            with pytest.raises(DevelopmentBlocked):
                await store.begin_run(task_id, 1)
        else:
            assert await store.consumed_cost(task_id) == Decimal("0.1")
            assert await store.begin_run(task_id, 1)
            with pytest.raises(ValueError, match="Another turn"):
                await store.begin_run(task_id, 1)


async def test_failed_turn_keeps_feedback_and_clears_old_completion(
    postgres_session_factory, tmp_path
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(factory, "receipt-review", 60)
        lease = await jobs.claim()
        await jobs.complete(lease, Action.START)
        lease = await jobs.claim()
        async with factory.begin() as session:
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            native.native_session_id = "review-native"
            native.checkpoint = {"next_feedback": "Keep mobile", "agent_result": {"old": "success"}}
        store = SqlDevelopmentStore(
            factory,
            session_id=native.id,
            job_id=lease.job_id,
            lease_token=lease.token,
            reservation_usd=Decimal("0.2"),
        )
        run_id = await store.begin_run(task_id, 1)
        await store.finish_run(
            run_id,
            TurnReceipt(
                "review-native",
                "failed-turn",
                "Needs repair",
                "failed",
                Usage(10, 5, 0, 0, provider_cost_usd=Decimal("0.01")),
            ),
        )
        async with factory() as session:
            native = await session.get(DeveloperSession, native.id)
            assert native.checkpoint["next_feedback"] == "Keep mobile"
            assert "agent_result" not in native.checkpoint
