from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.accounting import SqlDevelopmentStore
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession, PricingCatalog
from app.agent_runtime.infrastructure.reservations import development_allowance, reserve_budget
from app.delivery.infrastructure import workflow as delivery_workflow
from app.engineering.application.develop import DevelopmentBlocked
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.conversation import SqlAlchemyTaskConversationStore
from app.engineering.infrastructure.enrollment import enroll
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.engineering.infrastructure.models import ReviewCycle, ValidationRun
from app.engineering.infrastructure.task_models import Job, Task
from app.intake.domain.events import Event, Intent
from app.intake.infrastructure import v2_events
from app.intake.infrastructure.metered import CloudInterpreter
from app.platform.configuration.settings import Settings
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.platform.telemetry.dashboard import SqlAlchemyDashboardQueries
from app.repositories.infrastructure.models import Repository
from app.teams.domain.automation import AutomationPolicy
from app.teams.infrastructure.automation import TeamAutomationPolicy, policy_payload
from app.teams.infrastructure.automation_admin import SqlAutomationAdmin
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.statistics import statistics
from app.teams.infrastructure.team_models import Team
from tests.infrastructure.test_v2_delivery import SHA, fixture_payloads

pytestmark = pytest.mark.asyncio


async def test_cloud_fallback_is_bounded_and_metered_without_real_provider_calls(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        integration_id, price_id = None, uuid4()
        try:
            async with postgres_session_factory.begin() as session:
                integration = await session.scalar(
                    select(Integration).where(Integration.provider_name == "openai")
                )
                assert integration and integration.encrypted_credentials is None
                integration_id = integration.id
                integration.encrypted_credentials = cipher.encrypt("test-only")
                session.add(
                    PricingCatalog(
                        id=price_id,
                        provider="openai",
                        model="unit-cheap",
                        version=str(price_id),
                        input_per_million=Decimal(1),
                        output_per_million=Decimal(1),
                        cached_input_per_million=Decimal(0),
                        source_url="https://openai.com/api/pricing/",
                        effective_at=datetime.now(UTC) - timedelta(days=1),
                    )
                )
            requests = []
            original = httpx.AsyncClient

            def response(request: httpx.Request) -> httpx.Response:
                requests.append(request)
                return httpx.Response(
                    200,
                    json={
                        "usage": {
                            "input_tokens": 10,
                            "output_tokens": 5,
                            "input_tokens_details": {"cached_tokens": 0},
                        },
                        "output": [
                            {
                                "type": "message",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": '{"intent":"FEEDBACK","confidence":0.99,"reason":"Test correction"}',
                                    }
                                ],
                            }
                        ],
                    },
                )

            monkeypatch.setattr(
                httpx,
                "AsyncClient",
                lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(response)),
            )
            result = await CloudInterpreter(
                postgres_session_factory, task_id, "unit-cheap", Decimal("0.02")
            ).interpret(
                Event(
                    "github",
                    "test-event",
                    "comment",
                    "10",
                    "Fix the test",
                    str(task_id),
                    authenticated=True,
                )
            )
            assert result.intent == Intent.FEEDBACK and len(requests) == 1
            async with postgres_session_factory() as session:
                run = await session.scalar(select(AIRun).where(AIRun.task_id == task_id))
                assert run and run.role_kind == "INTERPRETER" and run.input_tokens == 10
                assert run.reserved_cost_usd and run.calculated_cost_usd == Decimal("0.000015")
        finally:
            async with postgres_session_factory.begin() as session:
                await session.execute(delete(AIRun).where(AIRun.task_id == task_id))
                await session.execute(delete(PricingCatalog).where(PricingCatalog.id == price_id))
                await session.execute(
                    update(Integration)
                    .where(Integration.id == integration_id)
                    .values(encrypted_credentials=None)
                )


async def test_v2_ui_note_does_not_spawn_legacy_jobs_and_feedback_is_explicit(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, settings):  # noqa: SIM117
        async with postgres_session_factory() as session:
            store = SqlAlchemyTaskConversationStore(session)
            message = await store.add_user_message(task_id, "What happened?", None)
            assert message.context["routing"] == "note-only"
            jobs = list(await session.scalars(select(Job).where(Job.task_id == task_id)))
            assert len(jobs) == 1 and jobs[0].action == "INTERPRET_EVENT"
            await store.add_user_message(
                task_id, f"/feedback {task_id} Keep the old API compatible", None
            )
            task = await session.get(Task, task_id)
            assert task and task.status == "PAUSED" and task.requirement_version == 2
            assert "Keep the old API compatible" in task.description
            row = AIRun(
                task_id=task_id,
                role_kind="DEVELOPER",
                provider="openai",
                model="unknown",
                status="FAILED",
                prompt_version="v2.1",
            )
            session.add(row)
            await session.commit()
            await SqlAutomationAdmin(session, settings).reconcile_cost(
                row.id, Decimal("0.03"), "provider-receipt-123"
            )
            await session.refresh(row)
            assert (
                row.calculated_cost_usd == Decimal("0.03")
                and row.input_tokens is None
                and not row.usage_complete
            )


@asynccontextmanager
async def scenario(factory: async_sessionmaker[AsyncSession], root: Path):
    team_id, repo_id, task_id = uuid4(), uuid4(), uuid4()
    settings = Settings(
        new_fixed_lifecycle=True,
        workspace_root=root / "workspaces",
        harness_state_root=root / "state",
    )
    try:
        async with factory.begin() as session:
            session.add(
                Repository(
                    id=repo_id,
                    external_repo_id=str(repo_id),
                    owner="acme",
                    name="repo",
                    clone_url="https://github.com/acme/repo.git",
                )
            )
            session.add(
                Team(id=team_id, name=f"enrollment-{team_id}", repository_ids=[str(repo_id)])
            )
            await session.flush()
            session.add(
                TeamAutomationPolicy(
                    team_id=team_id,
                    configuration=policy_payload(
                        AutomationPolicy(
                            enrollment_enabled=True,
                            repository_ids=(repo_id,),
                            task_budget_usd=Decimal(1),
                            team_budget_usd=Decimal(1),
                        )
                    ),
                )
            )
            session.add(
                TeamAgentProfile(
                    team_id=team_id,
                    role_kind="DEVELOPER",
                    display_name="Developer",
                    provider="openai",
                    model="gpt-5.6-terra",
                    harness="codex",
                    hard_budget_usd=Decimal(1),
                )
            )
            task = Task(id=task_id, title="One native task", team_id=team_id, repository_id=repo_id)
            session.add(task)
            await session.flush()
            await enroll(session, task, settings, actor="test")
        yield team_id, repo_id, task_id, settings
    finally:
        async with factory.begin() as session:
            await session.execute(delete(Task).where(Task.team_id == team_id))
            await session.execute(delete(Team).where(Team.id == team_id))
            await session.execute(delete(Repository).where(Repository.id == repo_id))


async def test_enrollment_is_idempotent_and_does_not_create_another_planner(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, settings):  # noqa: SIM117
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id, with_for_update=True)
            assert task
            await enroll(session, task, settings, actor="test")
            natives = list(
                await session.scalars(
                    select(DeveloperSession).where(DeveloperSession.task_id == task_id)
                )
            )
            jobs = list(await session.scalars(select(Job).where(Job.task_id == task_id)))
            assert len(natives) == len(jobs) == 1
            assert jobs[0].action == "INTERPRET_EVENT"
            assert task.status == "NEW"
            assert not Path(natives[0].workspace_path).exists()


async def test_reservation_is_atomic_and_unknown_cost_blocks_team(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(postgres_session_factory, "v2-cost-test", 60)
        intake = await jobs.claim()
        assert intake
        await jobs.complete(intake, Action.START)
        lease = await jobs.claim()
        assert lease
        async with postgres_session_factory() as session:
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            assert native
        store = SqlDevelopmentStore(
            postgres_session_factory,
            session_id=native.id,
            job_id=lease.job_id,
            lease_token=lease.token,
            reservation_usd=Decimal("1.01"),
        )
        with pytest.raises(DevelopmentBlocked, match="reservation"):
            await store.begin_run(task_id, 1)
        store.reservation_usd = Decimal("0.5")
        run_id = await store.begin_run(task_id, 1)
        await store.fail_run(run_id, "lost-receipt")
        with pytest.raises(DevelopmentBlocked, match="Unknown"):
            await store.begin_run(task_id, 1)
        async with postgres_session_factory() as session:
            row = await session.get(AIRun, run_id)
            assert (
                row and row.reserved_cost_usd == Decimal("0.5") and row.calculated_cost_usd is None
            )


async def test_development_uses_remaining_team_budget_and_rechecks_concurrent_spending(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (team_id, repo_id, task_id, _):
        other_id = uuid4()
        async with postgres_session_factory.begin() as session:
            session.add(
                Task(id=other_id, title="Previous work", team_id=team_id, repository_id=repo_id)
            )
            await session.flush()
            session.add(
                AIRun(
                    task_id=other_id,
                    role_kind="DEVELOPER",
                    provider="openai",
                    model="unit",
                    prompt_version="test",
                    status="COMPLETED",
                    calculated_cost_usd=Decimal("0.09"),
                )
            )
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            assert task
            allowance = await development_allowance(session, task, Decimal(1))
            assert allowance == Decimal("0.91")
            assert await development_allowance(session, task, Decimal("0.5")) == Decimal("0.5")
            await reserve_budget(session, task_id, allowance)
            # Another task wins the reservation between planning and admission.
            session.add(
                AIRun(
                    task_id=other_id,
                    role_kind="INTERPRETER",
                    provider="openai",
                    model="unit",
                    prompt_version="test",
                    status="RUNNING",
                    reserved_cost_usd=Decimal("0.1"),
                )
            )
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            assert task
            assert await development_allowance(session, task, Decimal(1)) == Decimal("0.81")
            with pytest.raises(DevelopmentBlocked, match="reservation"):
                await reserve_budget(session, task_id, allowance)
            prior = await session.scalar(
                select(AIRun).where(AIRun.task_id == other_id, AIRun.status == "RUNNING")
            )
            assert prior
            prior.status = "FAILED"
            await session.flush()
            with pytest.raises(DevelopmentBlocked, match="Unknown"):
                await development_allowance(session, task, Decimal(1))


async def test_dashboard_reports_native_usage_without_duplicate_accounting(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_team_id, _, task_id, _):
        async with postgres_session_factory.begin() as session:
            job = await session.scalar(select(Job).where(Job.task_id == task_id))
            assert job
            session.add(
                AIRun(
                    task_id=task_id,
                    role_kind="DEVELOPER",
                    provider="openai",
                    model="native",
                    status="COMPLETED",
                    input_tokens=50,
                    output_tokens=10,
                    prompt_version="v2.1",
                    provider_cost_usd=Decimal("0.02"),
                )
            )
        async with postgres_session_factory() as session:
            query = SqlAlchemyDashboardQueries(session)
            start = datetime.now(UTC) - timedelta(days=1)
            tokens, cost = await query._usage_total(start)
            assert tokens == 60 and cost == pytest.approx(0.02)
            assert {row.key for row in await query._usage(start, "role")} == {
                "DEVELOPER",
            }
            assert len(await query._usage(start, "team")) == 1
            assert len(await query._history(start, 1, usage=True)) == 1
            measured = await statistics(session, _team_id)
            assert measured["cloud_runs"][0]["attempts"] == 1
            assert measured["cloud_runs"][0]["cost_usd"] == "0.02000000"


async def test_receipt_does_not_drop_new_requirements_or_compaction_feedback(
    postgres_session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (_, _, task_id, _):
        jobs = SqlPhaseJobs(postgres_session_factory, "v2-receipt-test", 60)
        lease = await jobs.claim()
        assert lease
        await jobs.complete(lease, Action.START)
        lease = await jobs.claim()
        assert lease
        async with postgres_session_factory.begin() as session:
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            assert native
            native.native_session_id = "native-receipt"
            native.checkpoint = {"next_feedback": "New feedback", "base_sha": SHA}
        store = SqlDevelopmentStore(
            postgres_session_factory,
            session_id=native.id,
            job_id=lease.job_id,
            lease_token=lease.token,
            operation="compaction",
            reservation_usd=Decimal("0.2"),
        )
        run_id = await store.begin_run(task_id, 1)
        receipt = TurnReceipt(
            "native-receipt",
            "compact-1",
            "Compact",
            "completed",
            Usage(10, 5, 0, 0, provider_cost_usd=Decimal("0.01")),
            cumulative_usage={"input_tokens": 10},
        )
        await store.finish_run(run_id, receipt)
        async with postgres_session_factory() as session:
            native = await session.get(DeveloperSession, native.id)
            assert (
                native
                and native.checkpoint["next_feedback"] == "New feedback"
                and native.checkpoint["compaction_count"] == 1
            )
        store.operation = "development"
        run_id = await store.begin_run(task_id, 1)
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            assert task
            task.requirement_version = 2
        receipt = TurnReceipt(
            "native-receipt",
            "development-1",
            "Stale completion",
            "completed",
            Usage(10, 5, 0, 0, provider_cost_usd=Decimal("0.01")),
        )
        await store.finish_run(run_id, receipt)
        async with postgres_session_factory() as session:
            native = await session.get(DeveloperSession, native.id)
            assert (
                native
                and native.checkpoint["next_feedback"] == "New feedback"
                and native.checkpoint["base_sha"] == SHA
            )


async def test_fixed_pipeline_reviews_fix_on_same_session_then_merge(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with scenario(postgres_session_factory, tmp_path) as (team_id, repo_id, task_id, _):
        jobs = SqlPhaseJobs(postgres_session_factory, "v2-pipeline-test", 60)
        async with postgres_session_factory.begin() as session:
            policy = await session.get(TeamAutomationPolicy, team_id)
            assert policy
            policy.configuration = {
                **policy.configuration,
                "auto_merge": True,
                "authorized_reviewer_ids": ["10"],
                "required_checks": ["test"],
            }
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            assert native
            native.native_session_id = "persistent-native-thread"
        for result in [Action.START, Action.IMPLEMENTED]:
            lease = await jobs.claim()
            assert lease
            await jobs.complete(lease, result)
        async with postgres_session_factory.begin() as session:
            task = await session.get(Task, task_id)
            assert task
            task.current_revision, task.pull_request_number, task.pull_request_url = (
                SHA,
                1,
                "https://github.com/acme/repo/pull/1",
            )
            session.add(
                ValidationRun(
                    task_id=task_id,
                    head_sha=SHA,
                    requirement_version=1,
                    command=["test"],
                    exit_code=0,
                    status="PASSED",
                )
            )
        for result in [Action.VALIDATION_PASSED, Action.PUBLISHED]:
            lease = await jobs.claim()
            assert lease
            await jobs.complete(lease, result)
        feedback = {
            "action": "submitted",
            "review": {
                "id": 1,
                "state": "CHANGES_REQUESTED",
                "commit_id": SHA,
                "body": "Fix the edge case",
                "user": {"id": 10},
            },
        }
        async with postgres_session_factory.begin() as session:
            task, repo = await session.get(Task, task_id), await session.get(Repository, repo_id)
            assert task and repo
            await v2_events.github_event(session, task, repo, "pull_request_review", feedback)
            await v2_events.github_event(session, task, repo, "pull_request_review", feedback)
            assert task.stage == "FIXING"
            assert (
                len(
                    list(
                        await session.scalars(
                            select(ReviewCycle).where(ReviewCycle.task_id == task_id)
                        )
                    )
                )
                == 1
            )
            native = await session.scalar(
                select(DeveloperSession).where(DeveloperSession.task_id == task_id)
            )
            assert native and native.native_session_id == "persistent-native-thread"
            assert "Fix the edge case" in native.checkpoint["next_feedback"]
        for result in [Action.IMPLEMENTED, Action.VALIDATION_PASSED, Action.PUBLISHED]:
            lease = await jobs.claim()
            assert lease
            await jobs.complete(lease, result)
        data, writes = fixture_payloads(), []

        def respond(request: httpx.Request) -> httpx.Response:
            if request.method == "PUT":
                writes.append(request)
                return httpx.Response(200, json={"merged": True, "sha": "c" * 40})
            return httpx.Response(200, json=data[request.url.path])

        def client(_token: str) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                base_url="https://api.github.com", transport=httpx.MockTransport(respond)
            )

        for module in (v2_events, delivery_workflow):
            monkeypatch.setattr(module, "github_token", AsyncMock(return_value="test-only"))
            monkeypatch.setattr(module, "github_client", client)
        async with postgres_session_factory.begin() as session:
            task, repo = await session.get(Task, task_id), await session.get(Repository, repo_id)
            assert task and repo
            await v2_events.github_event(session, task, repo, "check_run", {"action": "completed"})
            assert task.stage == "MERGING"
        lease = await jobs.claim()
        assert lease and lease.action == "MERGE_PR"
        await jobs.complete(
            lease, await delivery_workflow.merge_phase(postgres_session_factory, lease)
        )
        async with postgres_session_factory() as session:
            task = await session.get(Task, task_id)
            assert task and task.status == "MERGED" and task.stage == "COMPLETE"
        assert len(writes) == 1
