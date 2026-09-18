from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.coordinator.infrastructure.actions import ActionExecutor
from app.coordinator.infrastructure.administration import CoordinationAdministration
from app.coordinator.infrastructure.inbox import enqueue
from app.coordinator.infrastructure.models import (
    CoordinatorAction,
    CoordinatorEvent,
    CoordinatorRun,
    HumanRequest,
)
from app.coordinator.infrastructure.processor import CoordinatorProcessor
from app.coordinator.infrastructure.schemas import parse_decision
from app.engineering.infrastructure.task_models import Job, Task
from app.platform.configuration.settings import get_settings
from app.platform.scheduling.states import JobState
from tests.integration.test_enrollment_and_costs import scenario


async def test_uncertain_delivery_is_reconciled_without_another_post(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice()
        gateway.reply.side_effect = TimeoutError("POST outcome unknown")
        gateway.reconcile.return_value = "confirmed-message"
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        await processor.process_one()
        await executor.execute_one()
        await executor.deliver_one()
        assert await executor.reconcile_one()
        assert not await executor.reconcile_one()
        assert not await executor.deliver_one()
        gateway.reply.assert_awaited_once()
        async with factory() as session:
            action = await session.scalar(
                select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
            )
            assert action.status == "EXECUTED" and action.provider_effect_ref == "confirmed-message"
            assert action.error is None


async def test_new_feedback_preserves_earlier_intent_for_fresh_decision(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id, "first")
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("REPAIR")
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        await processor.process_one()
        await send(factory, task_id, "second")
        assert await executor.execute_one()
        gateway.reply.assert_not_called()
        async with factory() as session:
            events = list(
                await session.scalars(
                    select(CoordinatorEvent).where(CoordinatorEvent.task_id == task_id)
                )
            )
            assert len(events) == 2 and all(
                e.status == "QUEUED" and e.run_id is None for e in events
            )
        assert await processor.process_one()
        assert len(model.decide.await_args.args[1]["events"]) == 2


async def test_summary_and_status_intents_preserve_authoritative_requirement(
    postgres_session_factory, tmp_path, active
):
    from app.delivery.infrastructure.status_sync import ExternalStatusSync

    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        model, gateway = AsyncMock(), AsyncMock()
        gateway.reply.return_value = "summary"
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        async with factory() as session:
            task = await session.get(Task, task_id)
            description, revision = task.description, task.requirement_version
        for kind in ("UPDATE_SUMMARY", "SYNC_STATUS"):
            await send(factory, task_id)
            model.decide.return_value = choice(kind)
            assert await processor.process_one()
            assert await executor.execute_one()
            await executor.deliver_one()
        async with factory() as session:
            task = await session.get(Task, task_id)
            assert (task.description, task.requirement_version) == (description, revision)
            assert (
                await session.get(ExternalStatusSync, task_id)
            ).lifecycle_version == task.lifecycle_version


async def test_coordination_metrics_use_durable_records(postgres_session_factory, tmp_path, active):
    from app.observability.infrastructure.coordination_metrics import coordination_metrics

    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        async with factory() as session:
            metrics = {metric.name: metric for metric in await coordination_metrics(session)}
        queued = [
            sample.value
            for sample in metrics["aew_coordinator_events"].samples
            if sample.labels == {"status": "QUEUED"}
        ]
        assert queued and queued[0] >= 1
        assert "aew_paid_slots_busy" in metrics


async def test_recorded_cases_and_delivery_outcomes_never_invent_ground_truth(
    postgres_session_factory, tmp_path, active
):
    from evaluations.delivery_outcomes import outcomes
    from evaluations.export_history import history_case

    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model = AsyncMock()
        model.decide.return_value = choice()
        await CoordinatorProcessor(factory, active, model, AsyncMock()).process_one()
        async with factory() as session:
            run = await session.scalar(
                select(CoordinatorRun).where(CoordinatorRun.task_id == task_id)
            )
            case = history_case(run)
            assert case["situation"] == run.evidence["packet"]
            assert case["expected_actions"] == [] and case["label_source"] == "UNLABELED"
            report = await outcomes(session, task_id)
            assert report["accepted_delivery"] is None
            assert report["total_known_cost_usd"] is None
            assert report["input_tokens"] is None


async def test_action_quality_uses_latest_human_label_and_rejects_other_task(
    postgres_session_factory, tmp_path, active
):
    from app.observability.infrastructure.coordination_metrics import coordination_metrics

    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model = AsyncMock()
        model.decide.return_value = choice()
        await CoordinatorProcessor(factory, active, model, AsyncMock()).process_one()
        await ActionExecutor(factory, AsyncMock()).execute_one()
        async with factory() as session:
            action = await session.scalar(
                select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
            )
        admin = CoordinationAdministration(factory, active)
        with pytest.raises(LookupError):
            await admin.review_action(uuid4(), action.id, "INCORRECT")
        await admin.review_action(task_id, action.id, "INCORRECT")
        await admin.review_action(task_id, action.id, "CORRECT")
        assert (await admin.task(task_id))["actions"][0]["review"] == "CORRECT"
        async with factory() as session:
            metrics = {metric.name: metric for metric in await coordination_metrics(session)}
            assert metrics["aew_coordinator_reviewed_actions"].samples[0].value == 1
            assert metrics["aew_coordinator_incorrect_action_rate"].samples[0].value == 0


def choice(action="REPLY"):
    return parse_decision(
        {
            "version": 1,
            "action": action,
            "message": "Should this work on mobile?"
            if action == "ASK_HUMAN"
            else "Mobile is included.",
            "engineering_request": "Include mobile support while preserving desktop behavior",
            "reason": "Clarify the requirement",
            "choices": ["Yes", "No"] if action == "ASK_HUMAN" else [],
            "read_tools": [],
            "checkpoint": {
                "goal": "Support mobile",
                "invariants": ["Desktop still works"],
                "open_questions": [],
            },
        }
    )


@pytest.fixture
def active(monkeypatch):
    monkeypatch.setenv("COORDINATOR_MODE", "active")
    monkeypatch.setenv("COORDINATOR_DEBOUNCE_SECONDS", "0")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


async def send(factory, task_id, key=None, **values):
    async with factory.begin() as session:
        task = await session.get(Task, task_id)
        return await enqueue(
            session,
            task,
            provider="dashboard",
            key=key or str(uuid4()),
            actor="local-operator",
            body="Also support mobile",
            **values,
        )


async def test_duplicate_events_coalesce_and_actions_execute_once(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id, "duplicate")
        await send(factory, task_id, "duplicate")
        await send(factory, task_id, "another")
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice()
        gateway.reply.return_value = "effect-1"
        processor = CoordinatorProcessor(factory, active, model, gateway)
        executor = ActionExecutor(factory, gateway)
        assert await processor.process_one()
        assert not await processor.process_one()
        model.decide.assert_awaited_once()
        assert await executor.execute_one()
        assert not await executor.execute_one()
        assert await executor.deliver_one()
        assert not await executor.deliver_one()
        gateway.reply.assert_awaited_once()
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CoordinatorEvent)
                    .where(CoordinatorEvent.task_id == task_id)
                )
                == 2
            )
            assert (
                await session.scalar(
                    select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
                )
            ).status == "EXECUTED"


async def test_human_answer_resumes_queued_engineering_without_duplicate_generation(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("ASK_HUMAN")
        gateway.reply.return_value = "question-1"
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        assert await processor.process_one()
        assert await executor.execute_one()
        assert await executor.deliver_one()
        async with factory() as session:
            task = await session.get(Task, task_id)
            human = await session.scalar(
                select(HumanRequest).where(HumanRequest.task_id == task_id)
            )
            assert task.status == "WAITING_HUMAN" and human.status == "OPEN"
        admin = CoordinationAdministration(factory, active)
        await admin.respond(task_id, human.id, "Yes, mobile is required")
        with pytest.raises(ValueError, match="already"):
            await admin.respond(task_id, human.id, "Duplicate answer")
        model.decide.return_value = choice("REPAIR")
        assert await processor.process_one()
        assert await executor.execute_one()
        async with factory() as session:
            task = await session.get(Task, task_id)
            assert task.status in {"NEW", "ACTIVE"}
            assert task.requirement_version == 2
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.task_id == task_id, Job.state == JobState.QUEUED)
                )
                == 1
            )


async def test_shadow_decisions_have_no_effects(postgres_session_factory, tmp_path, active):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("ASK_HUMAN")
        processor = CoordinatorProcessor(
            factory, active.model_copy(update={"coordinator_mode": "shadow"}), model, gateway
        )
        assert await processor.process_one()
        assert not await ActionExecutor(factory, gateway).execute_one()
        gateway.reply.assert_not_called()
        async with factory() as session:
            assert (await session.get(Task, task_id)).status == "NEW"
            assert (
                await session.scalar(
                    select(CoordinatorRun).where(CoordinatorRun.task_id == task_id)
                )
            ).status == "SHADOW"


@pytest.mark.parametrize("change_before_apply", [True, False])
async def test_stale_decision_or_delivery_never_sends(
    postgres_session_factory, tmp_path, active, change_before_apply
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice()
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        assert await processor.process_one()
        if not change_before_apply:
            assert await executor.execute_one()
        async with factory.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            task.lifecycle_version += 1
        await executor.execute_one()
        await executor.deliver_one()
        gateway.reply.assert_not_called()
        async with factory() as session:
            assert (
                await session.scalar(
                    select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
                )
            ).status in {"REJECTED", "SUPERSEDED"}


async def test_unknown_delivery_is_never_automatically_retried(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice()
        gateway.reply.side_effect = TimeoutError
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        await processor.process_one()
        await executor.execute_one()
        await executor.deliver_one()
        await executor.recover()
        assert not await executor.deliver_one()
        gateway.reply.assert_awaited_once()
        async with factory() as session:
            assert (
                await session.scalar(
                    select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
                )
            ).status == "UNKNOWN"


async def test_trello_clarification_and_reply_replace_old_classifier(
    postgres_session_factory, tmp_path, active
):
    from app.engineering.infrastructure.models import ReviewCycle
    from app.intake.infrastructure.tracker_comments import tracker_comment
    from app.platform.integrations.models import Integration

    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        async with factory.begin() as session:
            integration = await session.scalar(
                select(Integration).where(Integration.provider_name == "trello")
            )
            previous = dict(integration.configuration)
            integration.configuration = {
                **previous,
                "actor_ids": ["member-1", "bot-1"],
                "identity_id": "bot-1",
            }
        try:
            async with factory.begin() as session:
                task = await session.get(Task, task_id)
                await tracker_comment(
                    session,
                    task,
                    "trello",
                    "scope-change",
                    {"actor_id": "member-1", "raw_text": "It also needs to work on mobile"},
                )
            model, gateway = AsyncMock(), AsyncMock()
            model.decide.return_value = choice("ASK_HUMAN")
            gateway.reply.return_value = "trello-question-1"
            processor, executor = (
                CoordinatorProcessor(factory, active, model, gateway),
                ActionExecutor(factory, gateway),
            )
            await processor.process_one()
            await executor.execute_one()
            await executor.deliver_one()
            assert gateway.reply.await_args.args[1] == "trello"
            async with factory.begin() as session:
                task = await session.get(Task, task_id)
                await tracker_comment(
                    session,
                    task,
                    "trello",
                    "reply-1",
                    {"actor_id": "member-1", "raw_text": "Yes, use the same layout on mobile"},
                )
                assert not await session.scalar(
                    select(ReviewCycle.id).where(ReviewCycle.task_id == task_id)
                )
            model.decide.return_value = choice("REPAIR")
            await processor.process_one()
            await executor.execute_one()
            async with factory() as session:
                task = await session.get(Task, task_id)
                assert task.status in {"NEW", "ACTIVE"} and task.requirement_version == 2
                assert (
                    await session.scalar(
                        select(HumanRequest).where(HumanRequest.task_id == task_id)
                    )
                ).status == "ANSWERED"
        finally:
            async with factory.begin() as session:
                integration = await session.scalar(
                    select(Integration).where(Integration.provider_name == "trello")
                )
                integration.configuration = previous


async def test_task_queue_query_returns_one_row_and_current_spend(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (team_id, _, task_id, _):
        result = await CoordinationAdministration(factory, active).queue(team_id)
        assert [row["id"] for row in result["entries"]] == [str(task_id)]
        assert result["entries"][0]["lane"] == "QUEUED"
        assert result["developer_slots"]["capacity"] == 1
        assert result["spending"]["today_usd"] == "0"


async def test_coalescing_never_marks_unseen_events_processed(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        for index in range(7):
            await send(factory, task_id, f"burst-{index}")
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice()
        processor = CoordinatorProcessor(factory, active, model, gateway)
        await processor.process_one()
        assert len(model.decide.await_args.args[1]["events"]) == 5
        async with factory() as session:
            remaining = await session.scalar(
                select(func.count())
                .select_from(CoordinatorEvent)
                .where(CoordinatorEvent.task_id == task_id, CoordinatorEvent.status == "QUEUED")
            )
            assert remaining == 2


async def test_scope_feedback_waits_for_running_generation_and_is_reconsidered(
    postgres_session_factory, tmp_path, active
):
    from decimal import Decimal

    from app.agent_runtime.infrastructure.models import AIRun

    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        async with factory.begin() as session:
            paid = AIRun(
                task_id=task_id,
                role_kind="DEVELOPER",
                provider="openai",
                model="test",
                prompt_version="test.v1",
                status="RUNNING",
                reserved_cost_usd=Decimal("0.1"),
            )
            session.add(paid)
        await send(factory, task_id)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("REPAIR")
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        await processor.process_one()
        await executor.execute_one()
        async with factory() as session:
            assert (
                await session.scalar(
                    select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
                )
            ).status == "WAITING_ENGINEER"
        assert not await executor.execute_one()
        assert not await processor.process_one()
        async with factory.begin() as session:
            receipt = await session.get(AIRun, paid.id)
            receipt.status, receipt.calculated_cost_usd = "COMPLETED", Decimal("0.01")
            task = await session.get(Task, task_id)
            task.lifecycle_version += 1
        assert await executor.execute_one()
        assert await processor.process_one()
        assert model.decide.await_count == 2
        assert await executor.execute_one()
        async with factory() as session:
            assert (await session.get(Task, task_id)).requirement_version == 2
