"""Fresh repair context on the same worktree, with durable receipts left intact."""

import json
import re
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.checkpoints import workspace_facts
from app.agent_runtime.infrastructure.models import (
    AIRun,
    DeveloperContextGeneration,
    DeveloperSession,
)
from app.agent_runtime.infrastructure.process import capture
from app.engineering.application.jobs import PhaseLease
from app.engineering.infrastructure.lease_guard import assert_current
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.persistence.base import utcnow


async def prepare_repair(
    sessions: async_sessionmaker[AsyncSession],
    lease: PhaseLease,
    native: DeveloperSession,
) -> DeveloperSession:
    """Exactly once per repair job; no cold retry on a no-progress interruption."""
    async with sessions.begin() as session:
        task = await session.get(Task, lease.task_id, with_for_update=True)
        job = await session.get(Job, lease.job_id, with_for_update=True)
        assert_current(job, task, lease)
        row = await session.get(DeveloperSession, native.id, with_for_update=True)
        assert row and task and job
        if job.payload.get("fresh_repair_prepared") or not row.native_session_id:
            return row
        if row.state == "RUNNING" or task.stage != "FIXING":
            raise ValueError("Fresh repair requires a stopped session in FIXING")
        if await session.scalar(
            select(AIRun.id)
            .where(
                AIRun.task_id == task.id,
                or_(
                    AIRun.status == "RUNNING",
                    func.coalesce(AIRun.provider_cost_usd, AIRun.calculated_cost_usd).is_(None),
                ),
            )
            .limit(1)
        ):
            raise ValueError("Reconcile previous billing before fresh repair")
        feedback = str(row.checkpoint.get("next_feedback") or "").strip()
        if not feedback or len(feedback) > 16500:
            raise ValueError("Fresh repair needs a bounded explicit failure/review delta")
        workspace = Path(row.workspace_path)
        facts = await workspace_facts(workspace, workspace)
        base = str(row.checkpoint.get("base_sha") or "")
        if not re.fullmatch(r"[a-f0-9]{40,64}", base):
            raise ValueError("Fresh repair requires a verified base SHA")
        diff = await capture(
            [
                "git",
                "-c",
                "safe.directory=" + str(workspace),
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--stat",
                base,
                "--",
            ],
            cwd=workspace,
            env={
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0",
            },
            timeout=10,
            output_limit=16000,
        )
        validation = await session.scalar(
            select(ValidationRun)
            .where(ValidationRun.task_id == task.id)
            .order_by(ValidationRun.started_at.desc())
            .limit(1)
        )
        packet = {
            "current_sha": facts["workspace_head"],
            "expected_task_sha": task.current_revision,
            "base_sha": base,
            "diff_summary": diff.decode(errors="replace")[:4000],
            "uncommitted_files": facts["changed_files"],
            "review_or_failure_delta": feedback,
            "last_validation": {
                "sha": validation.head_sha,
                "status": validation.status,
                "exit_code": validation.exit_code,
                "output": validation.output_tail[-1800:],
            }
            if validation
            else None,
        }
        if len(json.dumps(packet).encode()) > 22000:
            raise ValueError("Repair evidence exceeds packet bound")
        generations = await session.scalars(
            select(DeveloperContextGeneration).where(
                DeveloperContextGeneration.developer_session_id == row.id,
                DeveloperContextGeneration.status == "ACTIVE",
            )
        )
        for generation in generations:
            generation.status, generation.ended_at, generation.end_reason = (
                "SEALED",
                utcnow(),
                "FRESH_REPAIR",
            )
        old_thread = row.native_session_id
        row.native_session_id, row.state = None, "CREATED"
        retained = {
            k: v
            for k, v in row.checkpoint.items()
            if k
            not in {
                "summary",
                "native_session_id",
                "native_turn_id",
                "rollover_checkpoint",
                "rollover_digest",
                "continuity_acknowledged",
                "continuation_pending",
                "handoff",
                "token_efficiency",
                "cumulative_usage",
                "compaction_count",
                "supervisor_memory",
                "validation_candidate",
            }
        }
        row.checkpoint = {
            **retained,
            "repair_packet": packet,
            "cumulative_usage": None,
            "token_efficiency": {},
            "compaction_count": 0,
        }
        if row.checkpoint.get("bounded_repair_pending"):
            row.checkpoint = {
                **row.checkpoint,
                "bounded_repair_pending": False,
                "bounded_repair_job_id": str(lease.job_id),
            }
        job.payload = {**job.payload, "fresh_repair_prepared": True}
        session.add(
            TaskEvent(
                task_id=task.id,
                source="controller",
                event_type="FRESH_REPAIR_GENERATION",
                payload={
                    "previous_native_session": old_thread,
                    "sha": facts["workspace_head"],
                    "usage_reset": False,
                },
            )
        )
        return row
