"""Optional, read-only native consultation; one bounded artifact crosses roles."""

import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.container import RunnerMounts
from app.agent_runtime.infrastructure.docker_harness import DockerHarness
from app.agent_runtime.infrastructure.helper_accounting import SqlHelperStore
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession, PricingCatalog
from app.agent_runtime.infrastructure.runner import Manifest
from app.engineering.application.develop import DevelopTask, SessionContext
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.consultation import outcome
from app.engineering.domain.lifecycle import WaitReason
from app.engineering.infrastructure.task_models import Task
from app.platform.configuration.settings import Settings
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.models import TeamAgentProfile


async def consult(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: httpx.AsyncClient,
    lease: PhaseLease,
    task: Task,
    native: DeveloperSession,
    role: Literal["THINKER", "REVIEWER"],
    *,
    change_context: str = "",
) -> tuple[str, str] | None:
    async with sessions() as session:
        profile = await session.scalar(
            select(TeamAgentProfile).where(
                TeamAgentProfile.team_id == task.team_id,
                TeamAgentProfile.role_kind == role,
            )
        )
        if profile is None or not profile.enabled:
            if role == "REVIEWER":
                return None
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION,
                "Developer requested a plan; configure and enable the Thinker or provide an explicit plan through task feedback",
            )
        if profile.hard_budget_usd is None or profile.harness not in {"codex", "claude"}:
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION,
                "Consultation needs a native harness and explicit USD limit",
            )
        if not (
            settings.developer_harness_codex
            if profile.harness == "codex"
            else settings.developer_harness_claude
        ):
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION, "Selected consultation harness is disabled"
            )
        integration = await session.scalar(
            select(Integration).where(Integration.provider_name == profile.provider)
        )
        if integration is None or not integration.encrypted_credentials:
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION, "Consultation provider credential is missing"
            )
        key = cipher.decrypt(integration.encrypted_credentials)
        price = await session.scalar(
            select(PricingCatalog)
            .where(
                PricingCatalog.provider == profile.provider,
                PricingCatalog.model == profile.model,
                PricingCatalog.context_tier == "standard",
                PricingCatalog.service_tier == "standard",
                PricingCatalog.effective_at <= datetime.now(UTC),
            )
            .order_by(PricingCatalog.effective_at.desc())
            .limit(1)
        )
        if profile.provider == "openai" and price is None:
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION, "Configure verified consultation pricing"
            )
        assert task.team_id is not None
        policy = await read_policy(session, task.team_id)
        rows = list(await session.scalars(select(AIRun).where(AIRun.task_id == task.id)))
        if role == "THINKER" and any(
            row.role_kind == role
            and row.requirement_version == task.requirement_version
            and row.status == "COMPLETED"
            for row in rows
        ):
            raise PhaseBlocked(
                WaitReason.MISSING_REQUIREMENT,
                "A plan already exists for this requirement; inspect it and provide new feedback instead of repeating planning",
            )
        total = role_total = Decimal(0)
        for row in rows:
            cost = (
                row.provider_cost_usd
                if row.provider_cost_usd is not None
                else row.calculated_cost_usd
            )
            if cost is None or row.status == "RUNNING":
                raise PhaseBlocked(
                    WaitReason.BUDGET_EXHAUSTED,
                    "Reconcile incomplete usage before another paid consultation",
                )
            total += cost
            if row.role_kind == role:
                role_total += cost
        remaining = min(policy.task_budget_usd - total, profile.hard_budget_usd - role_total)
        if remaining <= 0:
            raise PhaseBlocked(
                WaitReason.BUDGET_EXHAUSTED, "Consultation/task spending limit reached"
            )
    namespace = uuid4()
    state = settings.harness_state_root.resolve() / str(task.id) / "helpers" / str(namespace)
    directory = (
        settings.harness_control_root.resolve()
        / str(task.id)
        / (str(lease.token) + "-" + role.lower())
    )
    if state.resolve() != state or directory.resolve() != directory:
        raise ValueError("Consultation storage must not traverse symlinks")
    state.mkdir(parents=True, exist_ok=False)
    directory.mkdir(parents=True, exist_ok=False)
    if os.getuid() == 0:
        os.chown(state, 10001, 10001)
    mounts = RunnerMounts(
        task.id,
        Path(native.workspace_path),
        state,
        directory / "task.json",
        settings.workspace_root.resolve() / "tasks",
        settings.harness_state_root.resolve(),
        settings.harness_control_root.resolve(),
        state_namespace=namespace,
    )
    # Source is read on demand through native tools. Never attach the checkout or transcript.
    prompt = (
        f"Requirement version {task.requirement_version}: {task.title}\n{task.description}\n"
        f"Base revision: {native.checkpoint.get('base_sha', '')}; current revision: {task.current_revision or ''}\n"
        f"Developer's concise report:\n{native.checkpoint.get('summary', '')}\n"
        f"Validated change summary (inspect named files on demand):\n{change_context[:6000]}"
    )
    if len(prompt) > 24000:
        raise PhaseBlocked(
            WaitReason.MISSING_REQUIREMENT, "Shorten the requirement before consultation"
        )
    manifest = Manifest(
        harness=profile.harness,
        model=profile.model,
        effort=profile.effort,
        prompt=prompt,
        role_kind=role,
        supplemental_instructions=profile.supplemental_instructions,
        max_cost_usd=remaining,
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
    harness = DockerHarness(
        client,
        mounts=mounts,
        manifest=manifest,
        image=settings.developer_container_image,
        network=settings.developer_container_network,
        environment={
            "OPENAI_API_KEY" if profile.provider == "openai" else "ANTHROPIC_API_KEY": key,
            "HTTPS_PROXY": settings.developer_egress_proxy,
            "HTTP_PROXY": settings.developer_egress_proxy,
        },
        job_id=lease.job_id,
        lease_token=lease.token,
    )
    store = SqlHelperStore(sessions, lease, profile, remaining, price.id if price else None)
    receipt = await DevelopTask(harness, store, policy.task_budget_usd).execute(
        SessionContext(task.id, None, task.requirement_version, prompt)
    )
    if receipt.status != "completed":
        raise PhaseBlocked(
            WaitReason.MISSING_REQUIREMENT,
            "Consultation did not finish; inspect its saved artifact",
        )
    allowed = {"PLAN_READY"} if role == "THINKER" else {"REVIEW_OK", "REVIEW_CHANGES"}
    try:
        return outcome(receipt.summary, allowed)
    except ValueError as exc:
        raise PhaseBlocked(WaitReason.MISSING_REQUIREMENT, str(exc)) from exc


async def save_consultation_feedback(
    sessions: async_sessionmaker[AsyncSession],
    lease: PhaseLease,
    native: DeveloperSession,
    marker: str,
    feedback: str,
) -> None:
    async with sessions.begin() as session:
        task = await session.get(Task, lease.task_id, with_for_update=True)
        current = await session.get(DeveloperSession, native.id, with_for_update=True)
        if (
            task is None
            or current is None
            or task.lifecycle_version != lease.lifecycle_version
            or task.status != "ACTIVE"
        ):
            raise ValueError("Task changed during consultation")
        if not feedback.strip():
            raise PhaseBlocked(
                WaitReason.MISSING_REQUIREMENT, "Consultation returned no actionable content"
            )
        current.checkpoint = {**current.checkpoint, "next_feedback": f"{marker}:\n{feedback}"}
