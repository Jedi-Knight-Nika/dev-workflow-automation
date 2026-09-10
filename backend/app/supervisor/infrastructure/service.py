"""One intake decision and at most two anomaly decisions per lease. No AI polling."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.domain.usage import Pricing, Usage
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession, PricingCatalog
from app.agent_runtime.infrastructure.reservations import reserve_budget
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import WaitReason
from app.engineering.infrastructure.lease_guard import assert_current
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.intake.infrastructure.cloud_wire import normalized_usage, response_text
from app.platform.configuration.settings import Settings
from app.platform.integrations.models import Integration
from app.platform.security.crypto import cipher
from app.supervisor.infrastructure.localization import (
    candidate_paths,
    repository_entrypoints,
    repository_paths,
)
from app.supervisor.infrastructure.memory import task_memory
from app.supervisor.infrastructure.schemas import (
    CHECKPOINT_POLICY,
    SYSTEM_POLICY,
    SupervisorCheckpoint,
    SupervisorDecision,
)


async def supervise(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    lease: PhaseLease,
    native_id: UUID,
    *,
    anomaly: dict[str, Any] | None = None,
) -> SupervisorDecision:
    number = anomaly.get("sequence") if anomaly else None
    if anomaly and (
        type(number) is not int or number not in {1, 2} or len(json.dumps(anomaly)) > 5000
    ):
        raise ValueError("Invalid bounded Supervisor anomaly")
    suffix = f"_anomaly_{number}" if anomaly else ""
    decision_key, run_key = "supervisor_decision" + suffix, "supervisor_run_id" + suffix
    async with sessions.begin() as session:
        job = await session.get(Job, lease.job_id)
        task = await session.get(Task, lease.task_id)
        assert_current(job, task, lease)
        assert job and task
        if job.payload.get(decision_key):
            return SupervisorDecision.model_validate(job.payload[decision_key])
        if job.payload.get(run_key):
            raise PhaseBlocked(
                WaitReason.MISSING_REQUIREMENT,
                "Supervisor attempt already recorded; inspect its receipt",
            )
        native = await session.get(DeveloperSession, native_id)
        if native is None or native.task_id != task.id:
            raise ValueError("Supervisor session does not belong to task")
        inventory = (
            []
            if anomaly
            else await asyncio.to_thread(repository_paths, Path(native.workspace_path))
        )
        fresh_intake = not anomaly and task.stage == "DEVELOPING"
        packet = json.dumps(
            {
                "task_id": str(task.id),
                "requirement_version": task.requirement_version,
                "objective": task.title + "\n" + task.description,
                "stage": task.stage,
                "current_sha": task.current_revision,
                "feedback": native.checkpoint.get("next_feedback"),
                "memory": None
                if anomaly or fresh_intake
                else native.checkpoint.get("supervisor_memory"),
                "task_memory": [] if fresh_intake else await task_memory(session, task.id),
                "runtime_anomaly": anomaly,
                "repository_paths": inventory,
                "repository_entrypoints": await asyncio.to_thread(
                    repository_entrypoints, Path(native.workspace_path), inventory
                ),
                "unverified_filename_matches": await asyncio.to_thread(
                    candidate_paths,
                    Path(native.workspace_path),
                    task.title + " " + task.description,
                ),
            },
            ensure_ascii=False,
        )
        if len(packet.encode()) > 24000:
            raise PhaseBlocked(
                WaitReason.MISSING_REQUIREMENT,
                "Supervisor situation exceeds configured input bound",
            )
        price = await session.scalar(
            select(PricingCatalog)
            .where(
                PricingCatalog.provider == "openai",
                PricingCatalog.model == settings.supervisor_model,
                PricingCatalog.context_tier == "standard",
                PricingCatalog.service_tier == "standard",
                PricingCatalog.effective_at <= datetime.now(UTC),
            )
            .order_by(PricingCatalog.effective_at.desc())
            .limit(1)
        )
        integration = await session.scalar(
            select(Integration).where(Integration.provider_name == "openai")
        )
        if price is None or integration is None or not integration.encrypted_credentials:
            raise PhaseBlocked(
                WaitReason.MISSING_CONFIGURATION,
                "Supervisor requires OpenAI credentials and configured model pricing",
            )
        pricing = Pricing(
            price.input_per_million,
            price.output_per_million,
            price.cached_input_per_million,
            price.cache_write_per_million,
        )
        output_limit = 250 if anomaly else 1200
        schema = (SupervisorCheckpoint if anomaly else SupervisorDecision).model_json_schema()
        if not anomaly:
            schema["required"] = list(schema["properties"])
        payload = {
            "model": settings.supervisor_model,
            "store": False,
            "reasoning": {"effort": "low"},
            "max_output_tokens": output_limit,
            "input": [
                {"role": "system", "content": CHECKPOINT_POLICY if anomaly else SYSTEM_POLICY},
                {"role": "user", "content": packet},
            ],
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "supervisor_decision",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        reserve = pricing.calculate(
            Usage(len(json.dumps(payload).encode()) + 2048, output_limit, 0, 0)
        )
        assert reserve is not None
        reserve *= Decimal("1.25")
        if reserve > settings.supervisor_request_limit_usd:
            raise PhaseBlocked(
                WaitReason.BUDGET_EXHAUSTED, "Supervisor request exceeds its USD limit"
            )
        await reserve_budget(session, task.id, reserve, role_kind="SUPERVISOR")
        job = await session.get(Job, lease.job_id, with_for_update=True, populate_existing=True)
        await session.refresh(task)
        assert_current(job, task, lease)
        assert job
        if job.payload.get(run_key):
            raise PhaseBlocked(
                WaitReason.MISSING_REQUIREMENT, "Supervisor request is already owned"
            )
        key = cipher.decrypt(integration.encrypted_credentials)
        run = AIRun(
            task_id=task.id,
            job_id=job.id,
            role_kind="SUPERVISOR",
            provider="openai",
            model=settings.supervisor_model,
            requirement_version=task.requirement_version,
            prompt_version="supervisor.anomaly.v2" if anomaly else "supervisor.annotations.v2",
            status="RUNNING",
            reserved_cost_usd=reserve,
            pricing_id=price.id,
        )
        session.add(run)
        await session.flush()
        run_id = run.id
        job.payload = {**job.payload, run_key: str(run_id)}
    started = monotonic()
    try:
        async with (
            asyncio.timeout(45),
            httpx.AsyncClient(timeout=40, trust_env=False) as client,
            client.stream(
                "POST",
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            ) as response,
        ):
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 64000:
                    raise ValueError("Supervisor response exceeds bound")
        data = json.loads(body)
        raw = data.get("usage") or {}
        usage = normalized_usage("openai", raw)
        async with sessions.begin() as session:
            row = await session.get(AIRun, run_id, with_for_update=True)
            assert row
            row.raw_usage, row.usage_complete = raw, usage.complete
            row.input_tokens, row.output_tokens = usage.input_tokens, usage.output_tokens
            row.cache_read_tokens, row.cache_write_tokens = (
                usage.cache_read_input_tokens,
                usage.cache_write_input_tokens,
            )
            row.reasoning_tokens = usage.reasoning_tokens
            row.calculated_cost_usd = pricing.calculate(usage)
            row.provider_duration_ms = int((monotonic() - started) * 1000)
            row.finished_at, row.status = datetime.now(UTC), "COMPLETED"
        decision = (
            SupervisorCheckpoint.model_validate_json(response_text("openai", data)).annotations()
            if anomaly
            else SupervisorDecision.model_validate_json(response_text("openai", data))
        )
        allowed = (
            {"CONTINUE", "NUDGE", "STOP"}
            if anomaly
            else {"DELEGATE_IMPLEMENTATION", "DELEGATE_REPAIR", "WAIT_HUMAN"}
        )
        if decision.action not in allowed:
            raise ValueError("Supervisor action does not match trigger")
        if any(path not in inventory for path in decision.target_paths):
            raise ValueError("Supervisor selected a path outside the supplied repository inventory")
        if len(decision.model_dump_json().encode()) > 7000:
            raise ValueError("Supervisor decision exceeds bound")
        async with sessions.begin() as session:
            task = await session.get(Task, lease.task_id, with_for_update=True)
            job = await session.get(Job, lease.job_id, with_for_update=True)
            assert_current(job, task, lease)
            assert job
            native = await session.get(DeveloperSession, native_id, with_for_update=True)
            assert native
            job.payload = {**job.payload, decision_key: decision.model_dump()}
            if not anomaly:
                native.checkpoint = {
                    **native.checkpoint,
                    "supervisor_memory": decision.model_dump(),
                }
            session.add(
                TaskEvent(
                    task_id=lease.task_id,
                    source="supervisor",
                    event_type="SUPERVISOR_DECIDED",
                    payload={
                        "run_id": str(run_id),
                        "trigger": anomaly or "INTAKE",
                        **decision.model_dump(),
                    },
                )
            )
        return decision
    except BaseException as exc:
        async with sessions.begin() as session:
            row = await session.get(AIRun, run_id, with_for_update=True)
            if row:
                row.status, row.failure_code = "FAILED", type(exc).__name__[:100]
                row.finished_at = datetime.now(UTC)
        raise
