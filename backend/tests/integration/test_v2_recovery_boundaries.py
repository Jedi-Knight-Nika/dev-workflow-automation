from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.accounting import SqlDevelopmentStore
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.agent_runtime.infrastructure.orphans import sweep
from app.agent_runtime.infrastructure.reservations import reserve_budget
from app.engineering.application.develop import DevelopmentBlocked
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.lifecycle import LifecycleConflict, record_transition
from app.engineering.infrastructure.models import ReviewCycle
from app.engineering.infrastructure.task_models import Job, Task
from app.intake.infrastructure.review_text import process_review_text
from app.platform.scheduling.states import JobState
from tests.integration.test_v2_enrollment_and_costs import scenario

pytestmark = pytest.mark.asyncio


async def test_stale_loaded_task_cannot_overwrite_concurrent_pause(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        async with postgres_session_factory() as stale:
            cached = await stale.get(Task, task_id)
            assert cached
            old_version = cached.lifecycle_version
            async with postgres_session_factory.begin() as other:
                await record_transition(
                    other, task_id, Action.PAUSE, expected_version=old_version, actor="operator"
                )
            with pytest.raises(LifecycleConflict):
                await record_transition(
                    stale, task_id, Action.START, expected_version=old_version, actor="stale-worker"
                )
            await stale.rollback()
        async with postgres_session_factory() as session:
            task = await session.get(Task, task_id)
            assert task and task.status == "PAUSED" and task.lifecycle_version == old_version + 1


async def test_live_classification_does_not_starve_queue_and_dead_claim_keeps_unknown_cost(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, settings):
        now = datetime.now(UTC)
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            assert task
            task.status = "CANCELLED"
            running = ReviewCycle(
                task_id=task_id,
                actor="10",
                head_sha="",
                external_event_id="active",
                decision="CLASSIFYING",
                feedback={"claimed_at": now.isoformat()},
                created_at=now - timedelta(minutes=1),
            )
            pending = ReviewCycle(
                task_id=task_id,
                actor="10",
                head_sha="",
                external_event_id="pending",
                decision="CLASSIFY_PENDING",
            )
            session.add_all([running, pending])
            await session.flush()
            running_id, pending_id = running.id, pending.id
        assert await process_review_text(postgres_session_factory, settings)
        async with postgres_session_factory.begin() as session:
            running = await session.get(ReviewCycle, running_id)
            pending = await session.get(ReviewCycle, pending_id)
            assert running and running.decision == "CLASSIFYING"
            assert pending and pending.decision == "OBSOLETE"
            running.feedback = {"claimed_at": (now - timedelta(minutes=20)).isoformat()}
            lost = AIRun(
                task_id=task_id,
                role_kind="INTERPRETER",
                model="test",
                provider="openai",
                status="RUNNING",
                prompt_version="test",
                reserved_cost_usd=Decimal("0.01"),
                started_at=now - timedelta(minutes=19),
            )
            session.add(lost)
            await session.flush()
            lost_id = lost.id
        assert await process_review_text(postgres_session_factory, settings)
        async with postgres_session_factory() as session:
            lost = await session.get(AIRun, lost_id)
            running = await session.get(ReviewCycle, running_id)
            assert running and running.decision == "NEEDS_CLASSIFICATION"
            assert lost and lost.status == "INTERRUPTED"
            assert lost.calculated_cost_usd is None and lost.input_tokens is None
        assert not await process_review_text(postgres_session_factory, settings)


async def test_interpreter_role_budget_is_cumulative_under_shared_admission_lock(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        async with postgres_session_factory.begin() as session:
            session.add(
                AIRun(
                    task_id=task_id,
                    role_kind="INTERPRETER",
                    model="test",
                    provider="openai",
                    status="COMPLETED",
                    prompt_version="test",
                    calculated_cost_usd=Decimal("0.04"),
                )
            )
        async with postgres_session_factory.begin() as session:
            with pytest.raises(DevelopmentBlocked, match="role spending"):
                await reserve_budget(
                    session,
                    task_id,
                    Decimal("0.02"),
                    role_kind="INTERPRETER",
                    role_budget=Decimal("0.05"),
                )
            await reserve_budget(
                session,
                task_id,
                Decimal("0.02"),
                role_kind="INTERPRETER",
                role_budget=Decimal("0.10"),
            )


async def test_orphan_stops_only_owned_revoked_runner_and_accepts_late_billing_without_resume(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with (
        scenario(postgres_session_factory, tmp_path / "revoked") as (_, _, task_id, _),
        scenario(postgres_session_factory, tmp_path / "healthy") as (_, _, healthy_task_id, _),
    ):
        token, healthy_token = uuid4(), uuid4()
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            job = await session.scalar(select(Job).where(Job.task_id == task_id))
            healthy = await session.scalar(select(Job).where(Job.task_id == healthy_task_id))
            assert task and native and job and healthy
            task.status = "PAUSED"
            native.native_session_id = "persisted-native-id"
            native.state = "RUNNING"
            native.checkpoint = {"next_feedback": "Keep the newly requested fix"}
            job.state = JobState.CANCELLED
            healthy.state = JobState.RUNNING
            healthy.lease_token = healthy_token
            healthy.lease_expires_at = datetime.now(UTC) + timedelta(minutes=1)
            run = AIRun(
                task_id=task_id,
                session_id=native.id,
                job_id=job.id,
                role_kind="DEVELOPER",
                provider="openai",
                model=native.model,
                status="RUNNING",
                prompt_version="v2.1",
                reserved_cost_usd=Decimal("0.50"),
            )
            session.add(run)
            await session.flush()
            run_id, native_id, job_id, healthy_id = run.id, native.id, job.id, healthy.id
        stopped = []

        def handle(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "Id": "owned-revoked",
                            "Names": [f"/developer-{job_id}-{token}"],
                            "Labels": {"managed_by": "scheduler-v2", "task_id": str(task_id)},
                        },
                        {
                            "Id": "owned-healthy",
                            "Names": [f"/developer-{healthy_id}-{healthy_token}"],
                            "Labels": {
                                "managed_by": "scheduler-v2",
                                "task_id": str(healthy_task_id),
                            },
                        },
                        {
                            "Id": "another-installation",
                            "Names": [f"/developer-{uuid4()}-{token}"],
                            "Labels": {"managed_by": "scheduler-v2", "task_id": str(task_id)},
                        },
                        {"Id": "unrelated", "Names": ["/postgres"], "Labels": {}},
                    ],
                )
            assert request.method == "POST"  # Never delete evidence containers.
            stopped.append(request.url.path)
            return httpx.Response(204)

        async with httpx.AsyncClient(
            base_url="http://docker", transport=httpx.MockTransport(handle)
        ) as client:
            await sweep(client, postgres_session_factory)
        assert stopped == ["/containers/owned-revoked/stop"]
        async with postgres_session_factory() as session:
            run = await session.get(AIRun, run_id)
            assert run and run.status == "INTERRUPTED" and run.calculated_cost_usd is None
        await SqlDevelopmentStore(
            postgres_session_factory, session_id=native_id, job_id=job_id, lease_token=token
        ).finish_run(
            run_id,
            TurnReceipt(
                "persisted-native-id",
                "late-turn",
                "completed",
                "Late completion",
                Usage(10, 5, 0, 0, provider_cost_usd=Decimal("0.03")),
                {},
                cumulative_usage={"input_tokens": 10, "output_tokens": 5},
            ),
        )
        async with postgres_session_factory() as session:
            run = await session.get(AIRun, run_id)
            task = await session.get(Task, task_id)
            native = await session.get(DeveloperSession, native_id)
            assert run and run.provider_cost_usd == Decimal("0.03")
            assert task and task.status == "PAUSED"
            assert native and native.state == "BLOCKED"
            assert native.checkpoint["next_feedback"] == "Keep the newly requested fix"
