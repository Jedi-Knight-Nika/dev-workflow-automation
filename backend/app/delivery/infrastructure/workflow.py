import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.delivery.domain.merge import MergePolicy
from app.delivery.infrastructure.git_transport import github_token
from app.delivery.infrastructure.github import GitHubDelivery, github_client
from app.delivery.infrastructure.review_state import review_state
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.infrastructure.models import ValidationRun
from app.engineering.infrastructure.task_models import Job, Task, TaskEvent
from app.platform.scheduling.states import JobState
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.automation import read_policy
from app.teams.infrastructure.team_models import Team


async def delivery_gate(
    session: AsyncSession, task: Task, repository: Repository
) -> tuple[MergePolicy, tuple[str, ...], str | None]:
    if task.team_id is None:
        raise ValueError("Task requires a Team")
    policy = await read_policy(session, task.team_id)
    checks = list(
        await session.scalars(
            select(ValidationRun.status).where(
                ValidationRun.task_id == task.id,
                ValidationRun.head_sha == task.current_revision,
                ValidationRun.requirement_version == task.requirement_version,
            )
        )
    )
    validated = (
        task.current_revision if checks and all(status == "PASSED" for status in checks) else None
    )
    return (
        MergePolicy(
            policy.auto_merge,
            repository.id in policy.repository_ids
            and repository.enabled
            and repository.archived_at is None,
            frozenset(policy.authorized_reviewer_ids),
            policy.require_formal_approval,
            policy.reviewer_scope == "any_human",
        ),
        tuple(policy.required_checks),
        validated,
    )


async def merge_phase(sessions: async_sessionmaker[AsyncSession], lease: PhaseLease) -> Action:
    # Serialize control changes with the final evidence check and conditional merge.
    # No model or repository process runs while this short DB transaction is open.
    async with sessions.begin() as session:
        task = await session.get(Task, lease.task_id, with_for_update=True)
        job = await session.get(Job, lease.job_id, with_for_update=True)
        if (
            task is None
            or job is None
            or task.lifecycle_version != lease.lifecycle_version
            or job.lease_token != lease.token
            or job.state not in {JobState.RUNNING, JobState.CLAIMED}
            or not job.lease_expires_at
            or job.lease_expires_at <= datetime.now(UTC)
        ):
            raise PhaseBlocked(WaitReason.MISSING_CONFIGURATION, "Merge lease changed")
        team = await session.get(Team, task.team_id) if task.team_id else None
        repository = (
            await session.get(Repository, task.repository_id) if task.repository_id else None
        )
        if not team or not repository or not task.pull_request_number or not task.current_revision:
            raise PhaseBlocked(WaitReason.MISSING_CONFIGURATION, "Task has no published PR")
        policy, checks, validated = await delivery_gate(session, task, repository)
        reviewed, validated_at = await review_state(session, task)
        async with asyncio.timeout(20), github_client(await github_token(session)) as client:
            gateway = GitHubDelivery(client, repository.owner, repository.name)
            evidence, pull = await gateway.evidence(
                task.pull_request_number,
                task.current_revision,
                validated,
                policy,
                checks,
                reviewed_messages=reviewed,
                validated_at=validated_at,
                runnable=task.status == "ACTIVE"
                and task.stage == "MERGING"
                and not task.manual_takeover
                and not task.archived_at
                and team.enabled
                and not team.execution_paused
                and not team.archived_at,
            )
            if pull.get("merged") and pull["head"]["sha"] == task.current_revision:
                # Reconcile a lost merge response, never submit a second mutation.
                return Action.MERGED
            blockers = policy.blockers(evidence)
            if blockers:
                session.add(
                    TaskEvent(
                        task_id=task.id,
                        source="github",
                        event_type="ENGINEERING_MERGE_RECHECK_REQUIRED",
                        payload={"blockers": blockers},
                    )
                )
                return Action.MERGE_RECHECK
            if job.lease_expires_at <= datetime.now(UTC):
                raise PhaseBlocked(
                    WaitReason.MISSING_CONFIGURATION, "Lease expired during merge recheck"
                )
            result = await gateway.merge(task.pull_request_number, evidence.current_sha)
        session.add(
            TaskEvent(
                task_id=task.id,
                source="github",
                event_type="ENGINEERING_MERGE_CONFIRMED",
                payload={
                    "head_sha": evidence.current_sha,
                    "merge_sha": result["sha"],
                    "approval_id": evidence.approval.evidence_id if evidence.approval else None,
                },
            )
        )
        repository.latest_sha = result["sha"]
        return Action.MERGED
