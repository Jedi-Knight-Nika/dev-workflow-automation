from decimal import Decimal

import pytest

from app.agent_runtime.infrastructure.models import AIRun
from app.agent_runtime.infrastructure.reservations import reserve_budget
from app.engineering.application.develop import DevelopmentBlocked
from app.engineering.domain.lifecycle import Action
from app.engineering.infrastructure.jobs import SqlPhaseJobs
from app.platform.configuration.settings import get_settings
from app.teams.infrastructure.automation import TeamAutomationPolicy
from tests.integration.test_enrollment_and_costs import scenario


async def test_global_slots_and_fairness_across_independent_controllers(
    postgres_session_factory, tmp_path
):
    factory = postgres_session_factory
    async with (
        scenario(factory, tmp_path / "a") as (_, _, first_task, _),
        scenario(factory, tmp_path / "b") as (_, _, second_task, _),
    ):
        first = SqlPhaseJobs(
            factory, "controller-a", 60, global_developer_slots=1, validation_slots=1
        )
        second = SqlPhaseJobs(
            factory, "controller-b", 60, global_developer_slots=1, validation_slots=1
        )
        lease = await first.claim()
        assert lease and lease.task_id == first_task
        assert await second.claim() is None
        await first.complete(lease, Action.START)
        # A has another eligible Developer turn, but B has not had a slot yet.
        next_lease = await second.claim()
        assert next_lease and next_lease.task_id == second_task
        assert await first.claim() is None


@pytest.mark.parametrize("scope", ["account", "team"])
async def test_periodic_budget_counts_outstanding_reservations(
    postgres_session_factory, tmp_path, monkeypatch, scope
):
    factory = postgres_session_factory
    monkeypatch.setenv("ACCOUNT_MONTHLY_BUDGET_USD", "0.1" if scope == "account" else "100")
    get_settings.cache_clear()
    try:
        async with scenario(factory, tmp_path) as (team_id, _, task_id, _):
            async with factory.begin() as session:
                policy = await session.get(TeamAutomationPolicy, team_id)
                if scope == "team":
                    policy.configuration = {**policy.configuration, "monthly_budget_usd": "0.1"}
                session.add(
                    AIRun(
                        task_id=task_id,
                        role_kind="COORDINATOR",
                        provider="openai",
                        model="test",
                        prompt_version="test.v1",
                        status="RUNNING",
                        reserved_cost_usd=Decimal("0.08"),
                    )
                )
            async with factory.begin() as session:
                with pytest.raises(DevelopmentBlocked, match="monthly"):
                    await reserve_budget(session, task_id, Decimal("0.03"))
    finally:
        get_settings.cache_clear()
