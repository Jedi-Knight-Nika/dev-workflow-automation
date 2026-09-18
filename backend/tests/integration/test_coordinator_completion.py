from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.accounting import SqlDevelopmentStore
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.agent_runtime.infrastructure.reservations import consumed_cost
from app.coordinator.infrastructure.administration import CoordinationAdministration
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.engineering.infrastructure.task_models import Job, Task
from app.engineering.infrastructure.validation_requests import request_validation
from tests.integration.test_enrollment_and_costs import scenario


@pytest.mark.parametrize(
    "candidate", ["implemented", "partial", "failed", "busy", "stale_checkpoint"]
)
async def test_validation_intent_requires_completed_settled_candidate(
    postgres_session_factory, tmp_path, candidate
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(factory, "validation-intent", 60)
        lease = await jobs.claim()
        await jobs.complete(lease, Action.START)
        async with factory.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            native.state = "READY"
            if candidate == "stale_checkpoint":
                native.checkpoint = {"agent_result": {"payload": {"outcome": "IMPLEMENTED"}}}
            session.add(
                AIRun(
                    task_id=task_id,
                    session_id=native.id,
                    role_kind="DEVELOPER",
                    provider="openai",
                    model="fixture",
                    prompt_version="test",
                    requirement_version=task.requirement_version,
                    status="FAILED" if candidate == "failed" else "COMPLETED",
                    calculated_cost_usd=Decimal(0),
                    usage_complete=True,
                    artifact="NEEDS_HUMAN"
                    if candidate in {"partial", "stale_checkpoint"}
                    else "IMPLEMENTED\nfix: example",
                )
            )
            if candidate == "busy":
                job = await session.scalar(
                    select(Job).where(Job.task_id == task_id, Job.state == "QUEUED")
                )
                job.state = "CLAIMED"
            await session.flush()
            if candidate != "implemented":
                with pytest.raises(ValueError):
                    await request_validation(session, task, actor="coordinator")
            else:
                await request_validation(session, task, actor="coordinator")
                await request_validation(session, task, actor="coordinator")
                queued = list(
                    await session.scalars(
                        select(Job).where(Job.task_id == task_id, Job.state == "QUEUED")
                    )
                )
                assert len(queued) == 1 and queued[0].action == "RUN_VALIDATION"
                assert task.stage == "VALIDATING"


async def test_completed_lane_is_team_scoped_and_separate_from_open_pagination(
    postgres_session_factory, tmp_path
):
    factory = postgres_session_factory
    async with (
        scenario(factory, tmp_path / "one") as (team_id, _, task_id, settings),
        scenario(factory, tmp_path / "two") as (_, _, other_id, _),
    ):
        async with factory.begin() as session:
            for task_id_value in (task_id, other_id):
                task = await session.get(Task, task_id_value)
                task.status, task.completed_at = "MERGED", datetime.now(UTC)
        result = await CoordinationAdministration(factory, settings).queue(team_id)
        assert result["entries"] == [] and result["total"] == 0
        assert [entry["id"] for entry in result["recently_completed"]] == [str(task_id)]


async def test_invalid_routed_receipt_commits_unknown_cost_and_stops_delivery(
    postgres_session_factory, tmp_path
):
    factory = postgres_session_factory
    async with scenario(factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(factory, "routing-receipt", 60)
        lease = await jobs.claim()
        await jobs.complete(lease, Action.START)
        lease = await jobs.claim()
        async with factory.begin() as session:
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            native.native_session_id = "native-route"
        store = SqlDevelopmentStore(
            factory,
            session_id=native.id,
            job_id=lease.job_id,
            lease_token=lease.token,
            reservation_usd=Decimal("0.2"),
        )
        run_id = await store.begin_run(task_id, 1)
        with pytest.raises(ValueError, match="controller verification"):
            await store.finish_run(
                run_id,
                TurnReceipt(
                    "native-route",
                    "turn-route",
                    "IMPLEMENTED",
                    "completed",
                    Usage(10, 5, 0, 0, provider_cost_usd=Decimal("0.01")),
                    raw_usage={"priced_requests": [None]},
                ),
            )
        async with factory() as session:
            row = await session.get(AIRun, run_id)
            assert row.status == "FAILED" and row.native_turn_id == "turn-route"
            assert row.calculated_cost_usd is None and row.provider_cost_usd is None
            assert row.usage_complete is False and await consumed_cost(session, task_id) is None
            assert (await session.get(DeveloperSession, native.id)).state == "BLOCKED"
