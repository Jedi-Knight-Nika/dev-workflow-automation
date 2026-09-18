from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.domain.model_policy import PricedModel
from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.domain.usage import Pricing
from app.agent_runtime.infrastructure.models import (
    DeveloperSession,
    DeveloperTokenPolicy,
    PricingCatalog,
)
from app.agent_runtime.infrastructure.pricing_catalog import standard_price
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import WaitReason
from app.engineering.infrastructure.task_models import Task
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


@dataclass(frozen=True)
class PhaseContext:
    task: Task
    native: DeveloperSession
    profile: TeamAgentProfile
    team: Team
    token_policy_row: DeveloperTokenPolicy | None
    token_policy: TokenEfficiencyPolicy
    repository: Repository | None
    key: str | None = field(repr=False)
    price: PricingCatalog | None
    routed_models: list[PricedModel]


async def load_phase_context(
    sessions: async_sessionmaker[AsyncSession],
    lease: PhaseLease,
    *,
    compaction: bool = False,
    continuity: bool = False,
) -> PhaseContext:
    async with sessions() as session:
        task = await session.get(Task, lease.task_id)
        if task is None:
            raise LookupError("Task no longer exists")
        native = await session.scalar(
            select(DeveloperSession)
            .where(DeveloperSession.task_id == task.id)
            .order_by(DeveloperSession.generation.desc())
            .limit(1)
        )
        profile = (
            await session.get(TeamAgentProfile, native.profile_id)
            if native and native.profile_id
            else None
        )
        team = await session.get(Team, task.team_id) if task.team_id else None
        token_policy_row = (
            await session.get(DeveloperTokenPolicy, task.team_id) if task.team_id else None
        )
        token_policy = TokenEfficiencyPolicy.parse(
            (native.checkpoint.get("token_policy_override") if native else None)
            or (token_policy_row.values if token_policy_row else None)
        )
        repository = (
            await session.get(Repository, task.repository_id) if task.repository_id else None
        )
        if native is None or profile is None or team is None:
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION,
                "Enroll a prepared workspace and fixed Developer profile before execution",
            )
        if native.harness in {"responses", "patch"} and (compaction or continuity):
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION,
                "Responses supports fresh/resumed development, not compaction or rollover",
            )
        if (
            profile.harness != native.harness
            or profile.model != native.model
            or profile.provider != native.provider
        ):
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION,
                "Profile changed; explicitly migrate the native session instead of silently replacing it",
            )
        integration = await session.scalar(
            select(Integration).where(Integration.provider_name == native.provider)
        )
        key = (
            cipher.decrypt(integration.encrypted_credentials)
            if integration and integration.encrypted_credentials
            else None
        )
        price = await standard_price(session, native.provider, native.model)
        prices_by_model = {native.model: price}
        routed_models = []
        if native.harness == "patch" and lease.action == "DEVELOPER_TURN":
            for route in token_policy.model_routes:
                if route.provider != native.provider:
                    raise PhaseBlocked(
                        WaitReason.MISSING_CONFIGURATION,
                        "Cross-provider automatic routing is disabled",
                    )
                if route.model not in prices_by_model:
                    prices_by_model[route.model] = await standard_price(
                        session, route.provider, route.model
                    )
                routed_price = prices_by_model[route.model]
                if routed_price is None:
                    raise PhaseBlocked(
                        WaitReason.MISSING_CONFIGURATION,
                        "Configure verified pricing for every routed model",
                    )
                routed_models.append(
                    PricedModel(
                        route,
                        Pricing(
                            routed_price.input_per_million,
                            routed_price.output_per_million,
                            routed_price.cached_input_per_million,
                            routed_price.cache_write_per_million,
                        ),
                        str(routed_price.id),
                    )
                )
    return PhaseContext(
        task=task,
        native=native,
        profile=profile,
        team=team,
        token_policy_row=token_policy_row,
        token_policy=token_policy,
        repository=repository,
        key=key,
        price=price,
        routed_models=routed_models,
    )
