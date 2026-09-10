from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.agent_runtime.infrastructure.repair_generation import prepare_repair
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.engineering.infrastructure.task_models import Task, TaskEvent
from tests.integration.test_enrollment_and_costs import scenario


@pytest.mark.asyncio
async def test_token_limited_candidate_goes_to_validator_without_another_ai_run(
    postgres_session_factory, tmp_path, monkeypatch
):
    from app.agent_runtime.infrastructure import bounded_recovery as recovery

    facts = {
        "workspace_head": "b" * 40,
        "changed_files": ["frontend/src/Window.svelte"],
        "diff_fingerprint": "current",
    }
    evidence = {
        "diff_fingerprint": "current",
        "paths": facts["changed_files"],
        "checks": [{"name": name, "exit_code": 0} for name in ("format", "typecheck", "lint")],
    }
    monkeypatch.setattr(recovery, "workspace_facts", AsyncMock(return_value=facts))
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(postgres_session_factory, "candidate-test", 60)
        intake = await jobs.claim()
        await jobs.complete(intake, Action.START)
        lease = await jobs.claim()
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            native.state = "BLOCKED"
            session.add(
                AIRun(
                    task_id=task_id,
                    session_id=native.id,
                    role_kind="DEVELOPER",
                    provider="openai",
                    model="gpt-5.6-terra",
                    status="INTERRUPTED",
                    requirement_version=task.requirement_version,
                    failure_code="TURN_INPUT_LIMIT",
                    prompt_version="test",
                    calculated_cost_usd=Decimal("0.1"),
                    token_efficiency={"frontend_checks": evidence},
                )
            )
        assert await recovery.schedule_candidate_validation(
            postgres_session_factory, lease, native.id
        )
        await jobs.complete(lease, Action.VALIDATE_CANDIDATE)
        validation = await jobs.claim()
        assert validation.action == "RUN_VALIDATION"
        async with postgres_session_factory() as session:
            runs = list(await session.scalars(select(AIRun).where(AIRun.task_id == task_id)))
            assert len(runs) == 1
            assert runs[0].status == "INTERRUPTED"
            assert runs[0].calculated_cost_usd == Decimal("0.1")


@pytest.mark.asyncio
async def test_budget_recovery_queues_once_and_opens_fresh_repair(
    postgres_session_factory, tmp_path, monkeypatch
):
    from app.agent_runtime.infrastructure import bounded_recovery as recovery
    from app.agent_runtime.infrastructure import repair_generation as repair

    path = "frontend/src/Window.svelte"
    facts = {"workspace_head": "b" * 40, "changed_files": [path], "diff_fingerprint": "current"}
    evidence = {
        **facts,
        "paths": [path],
        "checks": [
            {"name": "format", "exit_code": 0},
            {"name": "typecheck", "exit_code": 0},
            {
                "name": "lint",
                "exit_code": 1,
                "error_count": 1,
                "errors": [
                    {
                        "path": path,
                        "line": 4,
                        "rule": "@typescript-eslint/no-unused-vars",
                        "message": "x unused",
                    }
                ],
            },
        ],
    }
    monkeypatch.setattr(recovery, "workspace_facts", AsyncMock(return_value=facts))
    monkeypatch.setattr(repair, "workspace_facts", AsyncMock(return_value=facts))
    monkeypatch.setattr(repair, "capture", AsyncMock(return_value=b"Window.svelte | 2 ++"))
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(postgres_session_factory, "recovery-test", 60)
        intake = await jobs.claim()
        await jobs.complete(intake, Action.START)
        lease = await jobs.claim()
        async with postgres_session_factory.begin() as session:
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            native.native_session_id, native.state = "old-thread", "BLOCKED"
            native.checkpoint = {"base_sha": "a" * 40}
            session.add(
                AIRun(
                    task_id=task_id,
                    session_id=native.id,
                    role_kind="DEVELOPER",
                    provider="openai",
                    model="gpt-5.6-terra",
                    status="INTERRUPTED",
                    failure_code="TURN_INPUT_LIMIT",
                    prompt_version="test",
                    calculated_cost_usd=Decimal("0.1"),
                    token_efficiency={"frontend_checks": evidence},
                )
            )
        assert await recovery.schedule_bounded_repair(postgres_session_factory, lease, native.id)
        assert not await recovery.schedule_bounded_repair(
            postgres_session_factory, lease, native.id
        )
        await jobs.complete(lease, Action.BOUNDED_REPAIR)
        next_lease = await jobs.claim()
        assert next_lease.action == "DEVELOPER_TURN" and next_lease.job_id != lease.job_id
        fresh = await prepare_repair(postgres_session_factory, next_lease, native)
        assert fresh.native_session_id is None
        assert fresh.checkpoint["bounded_repair_job_id"] == str(next_lease.job_id)
        assert "x unused" in fresh.checkpoint["repair_packet"]["review_or_failure_delta"]


@pytest.mark.asyncio
async def test_fresh_repair_is_once_per_job_and_keeps_billing(
    postgres_session_factory, tmp_path, monkeypatch
):
    import app.agent_runtime.infrastructure.repair_generation as module

    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(postgres_session_factory, "repair-test", 60)
        intake = await jobs.claim()
        await jobs.complete(intake, Action.START)
        lease = await jobs.claim()
        assert lease and await jobs.heartbeat(lease)
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            task.stage = "FIXING"
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            native.native_session_id = "old-thread"
            native.checkpoint = {
                "base_sha": "a" * 40,
                "next_feedback": "Resize window, not content",
                "cumulative_usage": {"input_tokens": 90000},
                "summary": "old transcript",
            }
            session.add(
                AIRun(
                    task_id=task_id,
                    session_id=native.id,
                    role_kind="DEVELOPER",
                    provider="openai",
                    model="gpt-5.6-terra",
                    status="COMPLETED",
                    prompt_version="test",
                    calculated_cost_usd=Decimal("0.1"),
                )
            )
        monkeypatch.setattr(
            module,
            "workspace_facts",
            AsyncMock(
                return_value={
                    "workspace_head": "b" * 40,
                    "changed_files": [],
                    "diff_fingerprint": "diff",
                }
            ),
        )
        monkeypatch.setattr(module, "capture", AsyncMock(return_value=b"Window.svelte | 2 ++"))
        fresh = await prepare_repair(postgres_session_factory, lease, native)
        assert fresh.native_session_id is None
        assert (
            fresh.checkpoint["repair_packet"]["review_or_failure_delta"]
            == "Resize window, not content"
        )
        assert "summary" not in fresh.checkpoint
        await prepare_repair(postgres_session_factory, lease, native)
        async with postgres_session_factory() as session:
            events = list(
                await session.scalars(
                    select(TaskEvent).where(
                        TaskEvent.task_id == task_id,
                        TaskEvent.event_type == "FRESH_REPAIR_GENERATION",
                    )
                )
            )
            assert len(events) == 1
            run = await session.scalar(select(AIRun).where(AIRun.task_id == task_id))
            assert run.calculated_cost_usd == Decimal("0.1")
