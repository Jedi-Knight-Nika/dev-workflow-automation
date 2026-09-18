from dataclasses import asdict, dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.infrastructure.accounting import SqlDevelopmentStore
from app.agent_runtime.infrastructure.models import DeveloperSession
from app.agent_runtime.infrastructure.reservations import development_allowance
from app.agent_runtime.infrastructure.runner import Manifest
from app.engineering.application.develop import DevelopmentBlocked
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import WaitReason
from app.engineering.infrastructure.developer_request import DeveloperRequest
from app.engineering.infrastructure.phase_context import PhaseContext
from app.platform.configuration.settings import Settings


@dataclass(frozen=True)
class DevelopmentAdmission:
    store: SqlDevelopmentStore
    allowance: Decimal
    budget: Decimal
    credential: str = field(repr=False)


async def admit_development(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    lease: PhaseLease,
    context: PhaseContext,
    native: DeveloperSession,
    *,
    bounded_repair: bool,
    compaction: bool,
    continuity: bool,
) -> DevelopmentAdmission:
    task, profile = context.task, context.profile
    key, price, routed_models = context.key, context.price, context.routed_models
    if not profile.enabled or profile.hard_budget_usd is None or key is None:
        raise PhaseBlocked(
            WaitReason.MISSING_CONFIGURATION,
            "Developer needs an enabled profile, provider credential and explicit USD budget",
        )
    if not (
        (native.harness == "codex" and settings.developer_harness_codex)
        or (native.harness == "claude" and settings.developer_harness_claude)
        or (native.harness in {"responses", "patch"} and settings.developer_harness_responses)
    ):
        raise PhaseBlocked(WaitReason.MISSING_CONFIGURATION, "Selected native harness is disabled")
    if native.provider in {"openai", "deepseek"} and price is None:
        raise PhaseBlocked(
            WaitReason.MISSING_CONFIGURATION,
            "Configure verified pricing before the first Developer turn",
        )
    store = SqlDevelopmentStore(
        sessions,
        session_id=native.id,
        job_id=lease.job_id,
        lease_token=lease.token,
        pricing_id=price.id if price else None,
        operation="compaction" if compaction else "continuity" if continuity else "development",
    )
    consumed = await store.consumed_cost(task.id)
    if consumed is None or consumed >= profile.hard_budget_usd:
        raise PhaseBlocked(
            WaitReason.BUDGET_EXHAUSTED,
            "Task cost is incomplete or its USD budget is exhausted",
        )
    try:
        async with sessions() as session:
            remaining = await development_allowance(
                session,
                task,
                profile.hard_budget_usd,
                settings.minimum_developer_turn_allowance_usd,
            )
    except DevelopmentBlocked as exc:
        raise PhaseBlocked(WaitReason.BUDGET_EXHAUSTED, str(exc)) from exc
    if settings.supervisor_enabled and not compaction and not continuity:
        remaining -= settings.supervisor_request_limit_usd * 2
        if remaining < settings.minimum_developer_turn_allowance_usd:
            raise PhaseBlocked(
                WaitReason.BUDGET_EXHAUSTED,
                "Insufficient budget for coding plus bounded supervision",
            )
    if bounded_repair:
        remaining = min(remaining, Decimal("0.15"))
    store.reservation_usd = remaining
    store.routing_price_ids = {UUID(route.pricing_id) for route in routed_models}
    if price:
        store.routing_price_ids.add(price.id)
    return DevelopmentAdmission(
        store=store, allowance=remaining, budget=profile.hard_budget_usd, credential=key
    )


def build_developer_manifest(
    settings: Settings,
    context: PhaseContext,
    native: DeveloperSession,
    token_policy: TokenEfficiencyPolicy,
    prepared: DeveloperRequest,
    allowance: Decimal,
    *,
    bounded_repair: bool,
    compaction: bool,
    continuity: bool,
) -> Manifest:
    profile, token_policy_row = context.profile, context.token_policy_row
    price, routed_models = context.price, context.routed_models
    if bounded_repair:
        effort = "low"
    else:
        team_policy = TokenEfficiencyPolicy.parse(
            token_policy_row.values if token_policy_row else None
        )
        effort_override = (native.checkpoint.get("token_policy_override") or {}).get(
            "reasoning_effort"
        )
        effort = team_policy.developer_effort(profile.effort, effort_override)
    return Manifest(
        work_request=prepared.work,
        routed_models=routed_models,
        pricing_id=str(price.id) if price else None,
        supervision_enabled=settings.supervisor_enabled
        and native.harness != "patch"
        and not compaction
        and not continuity,
        operation="compaction" if compaction else "continuity" if continuity else "development",
        harness=native.harness,
        model=native.model,
        provider=native.provider,
        effort=effort,
        token_policy=asdict(token_policy),
        progress_baseline=native.checkpoint.get("token_efficiency") or {},
        rollover_checkpoint=prepared.rollover,
        rollover_digest=native.checkpoint.get("rollover_digest") if prepared.rollover else None,
        prompt=prepared.prompt,
        supplemental_instructions=profile.supplemental_instructions,
        previous_usage=native.checkpoint.get("cumulative_usage"),
        max_cost_usd=allowance,
        timeout_seconds=settings.developer_turn_timeout_seconds,
        pricing={
            "input_per_million": price.input_per_million,
            "output_per_million": price.output_per_million,
            "cached_input_per_million": price.cached_input_per_million,
            "cache_write_per_million": price.cache_write_per_million,
        }
        if price
        else None,
    )
