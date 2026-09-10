"""Deterministic validation phase and evidence persistence; no Developer execution."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.container import validation_container_spec
from app.agent_runtime.infrastructure.container_job import run_container_job
from app.agent_runtime.infrastructure.control_files import atomic_json
from app.agent_runtime.infrastructure.models import DeveloperSession
from app.agent_runtime.infrastructure.phase_mounts import phase_mounts
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.domain.publication_title import publication_title
from app.engineering.infrastructure.consultation import consult, save_consultation_feedback
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Task
from app.engineering.infrastructure.validator_runner import ValidationManifest
from app.platform.configuration.settings import Settings
from app.repositories.infrastructure.models import RepositoryRuntimeProfile
from app.teams.infrastructure.team_models import Team


async def validate_phase(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: httpx.AsyncClient,
    lease: PhaseLease,
    task: Task,
    native: DeveloperSession,
    team: Team,
) -> Action:
    candidate = native.checkpoint.get("validation_candidate")
    if candidate:
        from app.agent_runtime.infrastructure.checkpoints import workspace_facts

        facts = await workspace_facts(Path(native.workspace_path), Path(native.workspace_path))
        if facts != candidate:
            raise PhaseBlocked(
                WaitReason.MISSING_REQUIREMENT,
                "Candidate changed after token-limit handoff; inspect before validation",
            )
    async with sessions() as session:
        runtime = (
            await session.get(RepositoryRuntimeProfile, task.repository_id)
            if task.repository_id
            else None
        )
    commands = (
        runtime.validation_commands
        if runtime
        else settings.repository_validation_commands.get(str(task.repository_id), [])
    )
    if not commands or not task.branch_name:
        raise PhaseBlocked(
            WaitReason.MISSING_CONFIGURATION,
            "Configure deterministic validation commands for this repository",
        )
    manifest = ValidationManifest(
        branch=task.branch_name,
        title=publication_title(task.title, str(native.checkpoint.get("summary") or "")),
        author_name=team.name,
        base_sha=str(native.checkpoint.get("base_sha") or ""),
        commands=commands,
        timeout_seconds=settings.developer_turn_timeout_seconds,
    )
    mounts = phase_mounts(settings, lease, native)
    atomic_json(mounts.manifest, manifest.model_dump(mode="json"))
    spec = validation_container_spec(
        mounts,
        image=runtime.validator_image_ref if runtime else settings.developer_container_image,
    )
    spec["Labels"]["job_id"] = str(lease.job_id)
    validation_started = datetime.now(UTC)
    result = await run_container_job(
        client,
        f"validation-{lease.job_id}-{lease.token}",
        spec,
        settings.developer_turn_timeout_seconds,
    )
    async with sessions.begin() as session:
        current = await session.get(Task, task.id, with_for_update=True)
        state = await session.get(DeveloperSession, native.id, with_for_update=True)
        if current is None or state is None or current.lifecycle_version != lease.lifecycle_version:
            raise ValueError("Task changed while validating")
        passed = result.get("passed") is True
        if passed:
            state.checkpoint = {
                **state.checkpoint,
                "publication_change_context": result.get("change_context", ""),
                "publication_checks": commands,
            }
        if passed and runtime:
            configured = await session.get(RepositoryRuntimeProfile, runtime.repository_id)
            if (
                configured
                and configured.validator_image_ref == runtime.validator_image_ref
                and configured.validation_commands == commands
            ):
                configured.last_verified_at = datetime.now(UTC)
                configured.image_digest = (
                    runtime.validator_image_ref.split("@", 1)[1]
                    if "@sha256:" in runtime.validator_image_ref
                    else None
                )
        for check in result["checks"]:
            session.add(
                ValidationRun(
                    task_id=task.id,
                    head_sha=result["head_sha"],
                    requirement_version=task.requirement_version,
                    command=check["command"],
                    exit_code=check["exit_code"],
                    status="PASSED"
                    if check["exit_code"] == 0 and not check["timed_out"]
                    else "FAILED",
                    output_tail=check["output_tail"][-8000:],
                    started_at=datetime.fromisoformat(check["started_at"])
                    if check.get("started_at")
                    else validation_started,
                    finished_at=datetime.fromisoformat(check["finished_at"])
                    if check.get("finished_at")
                    else datetime.now(UTC),
                )
            )
        current.current_revision = result["head_sha"]
        previous = current.progress_fingerprint or {}
        fingerprint = result["fingerprint"]
        current.no_progress_count = (
            current.no_progress_count + 1
            if not passed and previous.get("validation") == fingerprint
            else 0
        )
        current.progress_fingerprint = {"validation": fingerprint}
        if not passed:
            state.checkpoint = {
                **state.checkpoint,
                "next_feedback": "Fix these deterministic validation failures. Full logs remain in validation evidence:\n"
                + json.dumps(
                    [
                        {
                            "command": c["command"],
                            "exit_code": c["exit_code"],
                            "timed_out": c["timed_out"],
                            "output_tail": c["output_tail"][-1000:],
                        }
                        for c in result["checks"]
                        if c["exit_code"] != 0 or c["timed_out"]
                    ]
                )[:8000],
            }
        stop_loop = current.no_progress_count >= 2
    if stop_loop:
        raise PhaseBlocked(
            WaitReason.MISSING_REQUIREMENT,
            "Repeated validation failure without workspace progress; inspect before another paid turn",
        )
    if passed:
        task.current_revision = result["head_sha"]
        review = await consult(
            sessions,
            settings,
            client,
            lease,
            task,
            native,
            "REVIEWER",
            change_context=str(result.get("change_context") or ""),
        )
        if review and review[0] == "REVIEW_CHANGES":
            await save_consultation_feedback(sessions, lease, native, *review)
            return Action.VALIDATION_FAILED
    return Action.VALIDATION_PASSED if passed else Action.VALIDATION_FAILED
