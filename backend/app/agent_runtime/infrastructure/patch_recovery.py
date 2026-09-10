"""Admit explicit pre-model retries or deterministic recovery of a saved patch."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession


def unspent_failure(run: AIRun) -> bool:
    return (
        run.harness == "patch"
        and run.status == "FAILED"
        and run.failure_code == "PATCH_FAILED"
        and run.usage_complete is True
        and run.input_tokens == 0
        and run.output_tokens == 0
        and run.calculated_cost_usd == 0
        and (run.token_efficiency or {}).get("inference_cycle_count") == 0
    )


def rejected_patch(run: AIRun) -> bool:
    evidence = run.token_efficiency or {}
    return (
        run.harness == "patch"
        and run.status == "FAILED"
        and run.failure_code == "PATCH_LIMIT"
        and run.usage_complete is True
        and evidence.get("diff_changes") == 0
        and evidence.get("frontend_checks") is None
        and evidence.get("inference_cycle_count") in {1, 2}
    )


async def can_resume_patch(session: AsyncSession, native: DeveloperSession, version: int) -> bool:
    if native.harness != "patch" or not native.native_session_id:
        return False
    runs = (
        await session.scalars(
            select(AIRun).where(
                AIRun.task_id == native.task_id,
                AIRun.native_session_id == native.native_session_id,
                AIRun.role_kind == "DEVELOPER",
            )
        )
    ).all()
    # Admission alone never permits another paid attempt. The runner either
    # recovers a saved rejected patch or refuses already-attempted generations,
    # including crashes after admission with unknown usage.
    return bool(runs) and all(
        r.requirement_version == version and (unspent_failure(r) or rejected_patch(r)) for r in runs
    )
