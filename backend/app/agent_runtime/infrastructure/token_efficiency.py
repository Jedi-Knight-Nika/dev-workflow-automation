"""Persistence for native token policy and evidence. No paid provider operations."""

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy
from app.agent_runtime.infrastructure.checkpoints import checkpoint_bytes, workspace_facts
from app.agent_runtime.infrastructure.models import (
    AIRun,
    DeveloperCheckpoint,
    DeveloperContextGeneration,
    DeveloperSession,
    DeveloperTokenPolicy,
)
from app.agent_runtime.infrastructure.sessions import SqlSessionAdministration
from app.agent_runtime.infrastructure.workspace_lock import workspace_lock
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.configuration.models import SettingsAuditEvent
from app.platform.configuration.settings import get_settings
from app.platform.persistence.base import utcnow
from app.platform.scheduling.states import JobState
from app.teams.infrastructure.team_models import Team


async def ensure_generation(
    session: AsyncSession, native: DeveloperSession, policy: dict[str, Any]
) -> DeveloperContextGeneration:
    generation = await session.scalar(
        select(DeveloperContextGeneration).where(
            DeveloperContextGeneration.developer_session_id == native.id,
            DeveloperContextGeneration.status == "ACTIVE",
        )
    )
    if generation is None:
        last = await session.scalar(
            select(DeveloperContextGeneration.sequence)
            .where(DeveloperContextGeneration.developer_session_id == native.id)
            .order_by(DeveloperContextGeneration.sequence.desc())
            .limit(1)
        )
        generation = DeveloperContextGeneration(
            developer_session_id=native.id,
            sequence=(last or 0) + 1,
            native_thread_id=native.native_session_id,
            provider=native.provider,
            model=native.model,
            harness=native.harness,
            requirement_version=native.requirement_version,
            policy=policy,
        )
        session.add(generation)
        await session.flush()
    return generation


class SqlTokenEfficiency:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def task_policy(self, task_id: UUID) -> dict[str, Any]:
        loaded = await SqlSessionAdministration(self.session)._load(task_id)
        if loaded is None:
            task = await self.session.get(Task, task_id)
            if task is None:
                raise LookupError("Task not found")
            override = None
        else:
            task, native, _ = loaded
            override = native.checkpoint.get("token_policy_override")
        team = await self.policy(task.team_id) if task.team_id else {"values": {}}
        return {
            "version": task.lifecycle_version,
            "override": override,
            "values": asdict(TokenEfficiencyPolicy.parse(override or team["values"])),
        }

    async def save_task_policy(
        self, task_id: UUID, version: int, values: dict[str, Any]
    ) -> dict[str, Any]:
        policy = asdict(TokenEfficiencyPolicy.parse(values)) if values else None
        admin = SqlSessionAdministration(self.session)
        loaded = await admin._load(task_id, lock=True)
        if loaded is None:
            raise ValueError("Enroll and suspend the task first")
        task, native, _ = loaded
        if task.lifecycle_version != version or await admin._blocker(task, native):
            raise ValueError("Suspend/reconcile the task and reload its policy before changing it")
        before = native.checkpoint.get("token_policy_override")
        native.checkpoint = {**native.checkpoint, "token_policy_override": policy}
        task.lifecycle_version += 1
        self.session.add(
            TaskEvent(
                task_id=task_id,
                source="operator",
                event_type="TOKEN_POLICY_CHANGED",
                payload={"before": before, "after": policy, "usage_reset": False},
            )
        )
        await self.session.commit()
        return await self.task_policy(task_id)

    async def rollover(
        self,
        task_id: UUID,
        requirement_version: int,
        note: str,
        *,
        job_id: UUID | None = None,
        lease_token: UUID | None = None,
    ) -> dict[str, Any]:
        admin = SqlSessionAdministration(self.session)
        loaded = await admin._load(task_id, lock=True)
        if loaded is None:
            raise ValueError("Enroll the task first")
        task, native, _ = loaded
        if job_id is None:
            if blocker := await admin._blocker(task, native):
                raise ValueError(blocker)
        else:
            job = await self.session.get(Job, job_id, with_for_update=True)
            if (
                job is None
                or job.task_id != task_id
                or job.lease_token != lease_token
                or job.state != JobState.RUNNING
                or job.lease_expires_at is None
                or job.lease_expires_at <= utcnow()
                or task.status != "ACTIVE"
                or task.stage not in {"DEVELOPING", "FIXING"}
                or task.manual_takeover
                or native.state == "RUNNING"
            ):
                raise ValueError("Automatic rollover lost its execution lease")
            if await self.session.scalar(
                select(AIRun.id)
                .where(
                    AIRun.task_id == task_id,
                    or_(
                        AIRun.status == "RUNNING",
                        func.coalesce(AIRun.provider_cost_usd, AIRun.calculated_cost_usd).is_(None),
                    ),
                )
                .limit(1)
            ):
                raise ValueError("Rollover requires reconciled billing")
        if task.requirement_version != requirement_version or not native.native_session_id:
            raise ValueError("Requirements changed or no native context exists")
        policy = (
            TokenEfficiencyPolicy.parse(
                native.checkpoint.get("token_policy_override")
                or (await self.policy(task.team_id))["values"]
            )
            if task.team_id
            else TokenEfficiencyPolicy()
        )
        generation = await ensure_generation(self.session, native, asdict(policy))
        if job_id and (not policy.automatic_rollover or policy.mode != "ENFORCE"):
            raise ValueError("Automatic rollover is not enabled")
        sealed = await self.session.scalar(
            select(func.count())
            .select_from(DeveloperContextGeneration)
            .join(DeveloperSession)
            .where(
                DeveloperSession.task_id == task_id, DeveloperContextGeneration.status == "SEALED"
            )
        )
        if (sealed or 0) >= policy.max_rollovers:
            raise ValueError(
                "Automatic/operator rollover allowance exhausted; counters are never reset"
            )
        settings = get_settings()
        lock = settings.harness_control_root / str(task.id) / "workspace.lock"
        with workspace_lock(lock):
            facts = await workspace_facts(
                Path(native.workspace_path), settings.workspace_root / "tasks"
            )
            checkpoint = {
                "schema_version": 1,
                "task_id": str(task.id),
                "requirement_version": requirement_version,
                "context_generation": generation.sequence,
                "base_sha": native.checkpoint.get("base_sha"),
                **facts,
                "goal": task.title[:500],
                "requirement_digest": hashlib.sha256(
                    (task.title + "\n" + (task.description or "")).encode()
                ).hexdigest(),
                "semantic_note": note.strip(),
                "review_feedback_pending": str(native.checkpoint.get("next_feedback") or ""),
            }
            if not checkpoint["base_sha"] or not note.strip():
                raise ValueError("A verified base and bounded continuation note are required")
            if (
                job_id
                and not native.checkpoint.get("next_feedback")
                and (
                    (native.checkpoint.get("rollover_checkpoint") or {}).get("diff_fingerprint")
                    == facts["diff_fingerprint"]
                )
            ):
                raise ValueError("Milestone did not advance the verified workspace")
            digest = hashlib.sha256(checkpoint_bytes(checkpoint)).hexdigest()
            row = DeveloperCheckpoint(
                task_id=task.id,
                developer_session_id=native.id,
                context_generation_id=generation.id,
                requirement_version=requirement_version,
                checkpoint_json=checkpoint,
                checkpoint_digest=digest,
                validated=True,
                created_by="controller" if job_id else "operator",
            )
            self.session.add(row)
            await self.session.flush()
            generation.status, generation.ended_at, generation.end_reason = (
                "SEALED",
                utcnow(),
                "BOUNDARY_ROLLOVER" if job_id else "OPERATOR_ROLLOVER",
            )
            native.native_session_id = None
            native.state = "CREATED"
            native.checkpoint = {
                **native.checkpoint,
                "rollover_checkpoint": checkpoint,
                "rollover_digest": digest,
                "cumulative_usage": None,
                "compaction_count": 0,
                "token_efficiency": {
                    **(native.checkpoint.get("token_efficiency") or {}),
                    "tokens_since_last_progress": 0,
                    "compaction_count": 0,
                },
            }
            await self.session.flush()
            fresh = await ensure_generation(self.session, native, asdict(policy))
            self.session.add(
                TaskEvent(
                    task_id=task.id,
                    source="controller" if job_id else "operator",
                    event_type="CONTEXT_ROLLOVER",
                    payload={
                        "checkpoint_id": str(row.id),
                        "digest": digest,
                        "generation": fresh.sequence,
                    },
                )
            )
            await self.session.commit()
        return {
            "checkpoint_id": str(row.id),
            "generation": fresh.sequence,
            "status": "SUSPENDED",
            "digest": digest,
        }

    async def policy(self, team_id: UUID) -> dict[str, Any]:
        if await self.session.get(Team, team_id) is None:
            raise LookupError("Team not found")
        row = await self.session.get(DeveloperTokenPolicy, team_id)
        return {
            "version": row.version if row else 0,
            "values": asdict(TokenEfficiencyPolicy.parse(row.values if row else None)),
        }

    async def save_policy(
        self, team_id: UUID, version: int, values: dict[str, Any]
    ) -> dict[str, Any]:
        policy = asdict(TokenEfficiencyPolicy.parse(values))
        if await self.session.get(Team, team_id, with_for_update=True) is None:
            raise LookupError("Team not found")
        row = await self.session.get(DeveloperTokenPolicy, team_id, with_for_update=True)
        if version != (row.version if row else 0):
            raise ValueError("Policy changed; reload before saving")
        previous = row.values if row else {}
        if row:
            row.values, row.version = policy, row.version + 1
        else:
            row = DeveloperTokenPolicy(team_id=team_id, values=policy, version=1)
            self.session.add(row)
        self.session.add(
            SettingsAuditEvent(
                section="developer_token_policy",
                source="operator",
                old_values={"team_id": str(team_id), "version": version, "values": previous},
                new_values={"team_id": str(team_id), "version": row.version, "values": policy},
            )
        )
        await self.session.commit()
        return {"version": row.version, "values": policy}

    async def task(self, task_id: UUID) -> dict[str, Any]:
        task = await self.session.get(Task, task_id)
        if task is None:
            raise LookupError("Task not found")
        runs = list(
            await self.session.scalars(
                select(AIRun).where(AIRun.task_id == task_id).order_by(AIRun.started_at)
            )
        )
        samples = [r.token_efficiency for r in runs if r.token_efficiency]

        def total(field: str) -> int | None:
            values = [getattr(r, field) for r in runs]
            return sum(values) if values and all(v is not None for v in values) else None

        generations = await self.generations(task_id)
        first = next(
            (
                s["tokens_to_first_edit"]
                for s in samples
                if s.get("tokens_to_first_edit") is not None
            ),
            None,
        )
        peaks = [
            s["context_peak_tokens"] for s in samples if s.get("context_peak_tokens") is not None
        ]
        cached, inputs = total("cache_read_tokens"), total("input_tokens")
        uncached = inputs - cached if inputs is not None and cached is not None else None
        cycle_counts = [
            int(s["inference_cycle_count"])
            for s in samples
            if s.get("inference_cycle_count") is not None
        ]
        return {
            "task_id": str(task_id),
            "total_input_tokens": inputs,
            "cached_input_tokens": cached,
            "uncached_input_tokens": uncached,
            "inference_cycle_count": sum(cycle_counts) if cycle_counts else None,
            "output_tokens": total("output_tokens"),
            "tokens_to_first_edit": first,
            "peak_active_context_tokens": max(peaks) if peaks else None,
            "context_generation_count": len(generations),
            "rollover_count": sum(g["status"] == "SEALED" for g in generations),
            "compaction_count": sum(
                r.prompt_version == "developer.compaction"
                or bool((r.raw_usage or {}).get("compaction"))
                or (r.raw_usage or {}).get("run_kind") == "DEVELOPER_COMPACTION"
                for r in runs
            ),
            "tokens_since_last_progress": samples[-1].get("tokens_since_last_progress")
            if samples
            else None,
            "cache_hit_ratio": cached / inputs if inputs and cached is not None else None,
            "warnings": sorted({w for s in samples for w in s.get("warnings", [])}),
            "no_progress_interruptions": sum(
                r.failure_code in {"NO_PROGRESS", "REPEATED_TOOL_LOOP", "EXPLORATION_LIMIT"}
                for r in runs
            ),
            "policy": await self.task_policy(task_id),
            "measurement_quality": samples[-1].get("measurement_quality")
            if samples
            else {"usage": "historical-receipts-only"},
            "runs": [
                {
                    "id": str(r.id),
                    "context_generation_id": str(r.context_generation_id)
                    if r.context_generation_id
                    else None,
                    "metrics": r.token_efficiency,
                    "status": r.status,
                }
                for r in runs
            ],
        }

    async def generations(self, task_id: UUID) -> list[dict[str, Any]]:
        if await self.session.get(Task, task_id) is None:
            raise LookupError("Task not found")
        rows = await self.session.scalars(
            select(DeveloperContextGeneration)
            .join(DeveloperSession)
            .where(DeveloperSession.task_id == task_id)
            .order_by(DeveloperContextGeneration.started_at)
        )
        return [
            {
                "id": str(r.id),
                "sequence": r.sequence,
                "status": r.status,
                "model": r.model,
                "harness": r.harness,
                "native_thread_id": r.native_thread_id,
                "started_at": r.started_at.isoformat(),
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "end_reason": r.end_reason,
            }
            for r in rows
        ]

    async def checkpoints(self, task_id: UUID) -> list[dict[str, Any]]:
        if await self.session.get(Task, task_id) is None:
            raise LookupError("Task not found")
        rows = await self.session.scalars(
            select(DeveloperCheckpoint)
            .where(DeveloperCheckpoint.task_id == task_id)
            .order_by(DeveloperCheckpoint.created_at.desc())
            .limit(100)
        )
        return [
            {
                "id": str(r.id),
                "digest": r.checkpoint_digest,
                "validated": r.validated,
                "created_at": r.created_at.isoformat(),
                "checkpoint": r.checkpoint_json,
            }
            for r in rows
        ]
