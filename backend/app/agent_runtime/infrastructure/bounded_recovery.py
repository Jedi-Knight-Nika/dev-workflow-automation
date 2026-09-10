"""One small recovery of an existing patch, never an exploration/budget retry loop."""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.checkpoints import workspace_facts
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.engineering.application.jobs import PhaseLease
from app.engineering.infrastructure.lease_guard import assert_current
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent


def checks_passed(evidence: Any, facts: dict[str, Any]) -> bool:
    if (
        not isinstance(evidence, dict)
        or evidence.get("diff_fingerprint") != facts["diff_fingerprint"]
    ):
        return False
    paths = evidence.get("paths")
    checks = evidence.get("checks")
    return bool(
        facts["changed_files"]
        and isinstance(paths, list)
        and all(isinstance(p, str) for p in paths)
        and set(paths) == set(facts["changed_files"])
        and isinstance(checks, list)
        and len(checks) == 3
        and all(
            isinstance(c, dict) and c.get("exit_code") == 0 and not c.get("runtime_error")
            for c in checks
        )
        and {c.get("name") for c in checks} == {"format", "typecheck", "lint"}
    )


async def schedule_candidate_validation(
    sessions: async_sessionmaker[AsyncSession], lease: PhaseLease, native_id: Any
) -> bool:
    """An interrupted generation may yield a candidate, never a success receipt."""
    async with sessions.begin() as session:
        task = await session.get(Task, lease.task_id, with_for_update=True)
        job = await session.get(Job, lease.job_id, with_for_update=True)
        assert_current(job, task, lease)
        native = await session.get(DeveloperSession, native_id, with_for_update=True)
        if (
            not task
            or not job
            or not native
            or native.task_id != task.id
            or native.state == "RUNNING"
            or task.stage not in {"DEVELOPING", "FIXING"}
        ):
            return False
        prior = await session.scalar(
            select(AIRun)
            .where(AIRun.session_id == native.id, AIRun.role_kind == "DEVELOPER")
            .order_by(AIRun.started_at.desc())
            .limit(1)
        )
        if (
            not prior
            or prior.status != "INTERRUPTED"
            or prior.failure_code != "TURN_INPUT_LIMIT"
            or prior.requirement_version != task.requirement_version
        ):
            return False
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
            return False
        workspace = Path(native.workspace_path)
        facts = await workspace_facts(workspace, workspace)
        if not checks_passed((prior.token_efficiency or {}).get("frontend_checks"), facts):
            return False
        native.checkpoint = {
            **native.checkpoint,
            "validation_candidate": facts,
            "summary": "Token-limited candidate; targeted checks passed. Full validation required.",
        }
        session.add(
            TaskEvent(
                task_id=task.id,
                source="controller",
                event_type="TOKEN_LIMIT_VALIDATION_HANDOFF",
                payload={"run_id": str(prior.id), **facts, "developer_completed": False},
            )
        )
        return True


def minor_lint_errors(evidence: Any, facts: dict[str, Any]) -> list[dict[str, Any]]:
    if (
        not isinstance(evidence, dict)
        or evidence.get("diff_fingerprint") != facts["diff_fingerprint"]
    ):
        return []
    changed = facts["changed_files"]
    if not 1 <= len(changed) <= 3 or not all(p.startswith("frontend/src/") for p in changed):
        return []
    if evidence.get("paths") != changed:
        return []  # Require checks on ALL changed files, not a convenient subset.
    raw_checks = evidence.get("checks")
    if (
        not isinstance(raw_checks, list)
        or len(raw_checks) != 3
        or not all(isinstance(c, dict) for c in raw_checks)
    ):
        return []
    checks = {c.get("name"): c for c in raw_checks}
    if set(checks) != {"format", "typecheck", "lint"} or any(
        c.get("runtime_error") for c in raw_checks
    ):
        return []
    if checks["format"].get("exit_code") != 0 or checks["typecheck"].get("exit_code") != 0:
        return []
    lint = checks["lint"]
    errors = lint.get("errors")
    if (
        lint.get("exit_code") != 1
        or not isinstance(errors, list)
        or not 1 <= len(errors) <= 3
        or lint.get("error_count") != len(errors)
    ):
        return []
    if not all(
        isinstance(e, dict)
        and e.get("path") in changed
        and e.get("rule") in {"no-unused-vars", "@typescript-eslint/no-unused-vars"}
        and type(e.get("line")) is int
        and isinstance(e.get("message"), str)
        for e in errors
    ):
        return []
    return errors


async def schedule_bounded_repair(
    sessions: async_sessionmaker[AsyncSession], lease: PhaseLease, native_id: Any
) -> bool:
    async with sessions.begin() as session:
        task = await session.get(Task, lease.task_id, with_for_update=True)
        job = await session.get(Job, lease.job_id, with_for_update=True)
        assert_current(job, task, lease)
        assert task and job
        native = await session.get(DeveloperSession, native_id, with_for_update=True)
        if (
            not native
            or native.task_id != task.id
            or native.state == "RUNNING"
            or task.stage != "DEVELOPING"
        ):
            return False
        if await session.scalar(
            select(TaskEvent.id)
            .where(TaskEvent.task_id == task.id, TaskEvent.event_type == "BOUNDED_REPAIR_SCHEDULED")
            .limit(1)
        ):
            return False
        prior = await session.scalar(
            select(AIRun)
            .where(AIRun.session_id == native.id, AIRun.role_kind == "DEVELOPER")
            .order_by(AIRun.started_at.desc())
            .limit(1)
        )
        if (
            not prior
            or prior.status != "INTERRUPTED"
            or prior.failure_code != "TURN_INPUT_LIMIT"
            or prior.requirement_version != task.requirement_version
        ):
            return False
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
            return False
        workspace = Path(native.workspace_path)
        facts = await workspace_facts(workspace, workspace)
        # Optional controller-run preflight lets an explicitly resumed task
        # recover without rewriting its historical usage receipt.
        evidence = native.checkpoint.get("recovery_check_evidence") or (
            prior.token_efficiency or {}
        ).get("frontend_checks")
        errors = minor_lint_errors(evidence, facts)
        if not errors:
            return False
        feedback = (
            "One bounded recovery of the EXISTING patch. Preserve the original requirement and current behavior. "
            "Format and typecheck passed. Fix only these named unused-variable lint errors; do not re-explore.\n"
            + json.dumps(errors, ensure_ascii=False)
            + "\nThen run repository_tools check on these files together: "
            + " ".join(facts["changed_files"])
            + ". Report completion for full deterministic validation. No additional automatic recovery is allowed."
        )
        native.checkpoint = {
            **native.checkpoint,
            "next_feedback": feedback,
            "bounded_repair_pending": True,
        }
        session.add(
            TaskEvent(
                task_id=task.id,
                source="controller",
                event_type="BOUNDED_REPAIR_SCHEDULED",
                payload={
                    "previous_run_id": str(prior.id),
                    "errors": errors,
                    "diff_fingerprint": facts["diff_fingerprint"],
                    "input_limit": 80000,
                    "usd_limit": "0.15",
                },
            )
        )
        return True
