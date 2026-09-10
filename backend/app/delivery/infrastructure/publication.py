"""Publish a validated revision without owning Developer or validation execution."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import DeveloperSession
from app.agent_runtime.infrastructure.phase_mounts import phase_mounts
from app.delivery.infrastructure.git_runner import GitManifest
from app.delivery.infrastructure.git_transport import github_token, run_git
from app.delivery.infrastructure.github import GitHubDelivery, github_client
from app.delivery.infrastructure.workflow import delivery_gate
from app.engineering.application.jobs import PhaseBlocked, PhaseLease
from app.engineering.domain.lifecycle import Action, WaitReason
from app.engineering.domain.publication_title import publication_body, publication_title
from app.engineering.infrastructure.task_models import Task
from app.platform.configuration.settings import Settings
from app.repositories.infrastructure.models import Repository


async def publish_phase(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    client: httpx.AsyncClient,
    lease: PhaseLease,
    task: Task,
    native: DeveloperSession,
    repository: Repository,
) -> Action:
    async with sessions() as session:
        _, _, validated = await delivery_gate(session, task, repository)
        token = await github_token(session)
    if not validated:
        raise PhaseBlocked(
            WaitReason.MISSING_CONFIGURATION,
            "Publication requires passing validation at the current requirement and SHA",
        )
    mounts = phase_mounts(settings, lease, native)
    await run_git(
        client,
        settings,
        mounts,
        GitManifest(
            operation="publish",
            owner=repository.owner,
            repository=repository.name,
            branch=task.branch_name or "",
            base_branch=str(native.checkpoint.get("base_branch") or repository.default_branch),
            expected_sha=validated,
        ),
        token,
        f"publish-{lease.job_id}-{lease.token}",
    )
    summary = str(native.checkpoint.get("summary") or "")
    title = publication_title(task.title, summary)
    async with github_client(token) as api:
        pull = await GitHubDelivery(api, repository.owner, repository.name).publish(
            branch=task.branch_name or "",
            base=str(native.checkpoint.get("base_branch") or repository.default_branch),
            title=title,
            body=publication_body(
                task_ref=str(task.external_key or task.id),
                title=title,
                summary=summary,
                sha=validated,
                change_context=str(native.checkpoint.get("publication_change_context") or ""),
                checks=native.checkpoint.get("publication_checks"),
            ),
            owner=repository.owner,
            expected_sha=validated,
        )
    async with sessions.begin() as session:
        current = await session.get(Task, task.id, with_for_update=True)
        if current is None or current.lifecycle_version != lease.lifecycle_version:
            raise ValueError("Task changed during publication; inspect the task branch/PR")
        current.pull_request_number, current.pull_request_url = pull["number"], pull["html_url"]
    return Action.PUBLISHED
