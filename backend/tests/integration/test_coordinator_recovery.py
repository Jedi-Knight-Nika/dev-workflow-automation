import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent_runtime.infrastructure.models import AIRun
from app.coordinator.infrastructure.actions import ActionExecutor
from app.coordinator.infrastructure.inbox import enqueue
from app.coordinator.infrastructure.models import (
    CoordinatorAction,
    CoordinatorEvent,
    CoordinatorRun,
    HumanRequest,
)
from app.coordinator.infrastructure.processor import CoordinatorProcessor
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Task
from app.platform.integrations.models import Integration
from tests.integration import test_coordinator as coordinator_fixtures
from tests.integration.test_coordinator import choice, send
from tests.integration.test_enrollment_and_costs import scenario

active = coordinator_fixtures.active


@pytest.mark.parametrize("directive,status", [("CANCEL", "CANCELLED"), ("PAUSE", "PAUSED")])
async def test_new_control_message_interrupts_wait_for_coding(
    postgres_session_factory, tmp_path, active, directive, status
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(factory, "recovery-review", 60)
        await jobs.complete(await jobs.claim(), Action.START)
        async with factory.begin() as session:
            receipt = AIRun(
                task_id=task_id,
                role_kind="DEVELOPER",
                provider="openai",
                model="fixture",
                prompt_version="test",
                status="RUNNING",
                reserved_cost_usd=Decimal("0.1"),
            )
            session.add(receipt)
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.side_effect = [choice("REPAIR"), choice(directive)]
        processor, executor = (
            CoordinatorProcessor(factory, active, model, gateway),
            ActionExecutor(factory, gateway),
        )
        await send(factory, task_id)
        assert await processor.process_one() and await executor.execute_one()
        assert not await executor.execute_one()  # No idle retry while coding is running.
        async with factory() as session:
            waiting = await session.scalar(
                select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
            )
            assert waiting.status == "WAITING_ENGINEER"
        async with factory.begin() as session:
            await enqueue(
                session,
                await session.get(Task, task_id),
                provider="dashboard",
                key=str(uuid4()),
                actor="local-operator",
                body=f"{directive.lower()} this task now",
            )
        assert await executor.execute_one()  # New input supersedes the waiting repair.
        assert await processor.process_one() and await executor.execute_one()
        async with factory() as session:
            assert (await session.get(Task, task_id)).status == status
            assert (await session.get(CoordinatorAction, waiting.id)).status == "SUPERSEDED"
            assert (await session.get(AIRun, receipt.id)).status == "RUNNING"
        assert model.decide.await_count == 2


async def test_context_excludes_old_questions_and_validation(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        async with factory.begin() as session:
            task = await session.get(Task, task_id)
            task.requirement_version, task.lifecycle_version, task.current_revision = 2, 2, "b" * 40
            run = CoordinatorRun(
                task_id=task_id,
                mode="active",
                status="COMPLETED",
                requirement_revision=1,
                lifecycle_revision=1,
            )
            session.add(run)
            await session.flush()
            session.add(
                HumanRequest(
                    task_id=task_id,
                    run_id=run.id,
                    question="Obsolete question",
                    reason="Old scope",
                    requirement_revision=1,
                    lifecycle_revision=1,
                )
            )
            for revision, sha, status in [
                (1, "b" * 40, "PASSED"),
                (2, "a" * 40, "PASSED"),
                (2, "b" * 40, "FAILED"),
            ]:
                session.add(
                    ValidationRun(
                        task_id=task_id,
                        requirement_version=revision,
                        head_sha=sha,
                        command=["fixture"],
                        status=status,
                    )
                )
        await send(factory, task_id)
        claimed = await CoordinatorProcessor(factory, active, AsyncMock(), AsyncMock()).claim()
        assert claimed and claimed[3]["human_request"] is None
        assert claimed[3]["validation"] == [{"status": "FAILED", "sha": "b" * 40}]


async def test_delivery_check_has_total_deadline_and_never_resends(
    postgres_session_factory, tmp_path, active, monkeypatch
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        model, gateway = AsyncMock(), AsyncMock()
        model.decide.return_value = choice("REPLY")
        gateway.reply.side_effect = TimeoutError("Unknown POST")

        async def hanging_read(*args):
            await asyncio.Future()

        gateway.reconcile.side_effect = hanging_read
        monkeypatch.setattr(
            "app.coordinator.infrastructure.actions.DELIVERY_CHECK_TIMEOUT_SECONDS", 0.01
        )
        await send(factory, task_id)
        await CoordinatorProcessor(factory, active, model, gateway).process_one()
        executor = ActionExecutor(factory, gateway)
        await executor.execute_one()
        await executor.deliver_one()
        assert await asyncio.wait_for(executor.reconcile_one(), timeout=1)
        assert not await executor.reconcile_one() and not await executor.deliver_one()
        gateway.reply.assert_awaited_once()
        async with factory() as session:
            action = await session.scalar(
                select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
            )
            assert action.status == "UNKNOWN" and "TimeoutError" in action.error


async def test_echo_confirms_delivery_during_history_reconciliation(
    postgres_session_factory, tmp_path, active
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        model = AsyncMock()
        model.decide.return_value = choice("REPLY")
        await send(factory, task_id)
        await CoordinatorProcessor(factory, active, model, AsyncMock()).process_one()
        await ActionExecutor(factory, AsyncMock()).execute_one()
        # Roll back the temporary integration identity with this transaction.
        async with factory() as session:
            action = await session.scalar(
                select(CoordinatorAction).where(CoordinatorAction.task_id == task_id)
            )
            integration = await session.scalar(
                select(Integration).where(Integration.provider_name == "trello")
            )
            integration.configuration = {"identity_id": "bot-test"}
            action.status = "RECONCILING"
            action.arguments = {**action.arguments, "provider": "trello"}
            await session.flush()
            await enqueue(
                session,
                await session.get(Task, task_id),
                provider="trello",
                key=str(uuid4()),
                actor="bot-test",
                body=action.arguments["message"],
                context={"provider_effect_ref": "confirmed-remote-id"},
            )
            assert (
                action.status == "EXECUTED" and action.provider_effect_ref == "confirmed-remote-id"
            )
            await session.flush()
            echo = await session.scalar(
                select(CoordinatorEvent).where(
                    CoordinatorEvent.task_id == task_id, CoordinatorEvent.status == "ECHO"
                )
            )
            assert echo
