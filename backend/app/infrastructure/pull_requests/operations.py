from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Integration, Repository, Task, TaskRepositoryScope, TaskState
from app.infrastructure.git.workspaces import github_token, run_git
from app.infrastructure.linear_sync import sync_published_task_to_linear
from app.infrastructure.persistence.job_operations import record_event
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth
from app.schemas import PullRequestRead


async def publish_pull_request(
    session: AsyncSession,
    task: Task,
    repository: Repository,
    scope: TaskRepositoryScope | None = None,
) -> PullRequestRead:
    workspace_path = scope.workspace_path if scope else task.workspace_path
    branch_name = scope.branch_name if scope else task.branch_name
    pull_request_number = scope.pull_request_number if scope else task.pull_request_number
    if not workspace_path or not branch_name:
        raise RuntimeError("Task workspace is not prepared")
    workspace = Path(workspace_path)
    status = await run_git("status", "--porcelain", cwd=workspace)
    if status:
        await run_git("add", "--all", cwd=workspace)
        await run_git(
            "-c",
            "user.name=Engineering Worker",
            "-c",
            "user.email=engineering-worker@localhost",
            "commit",
            "-m",
            task.title[:72],
            cwd=workspace,
        )
    token = await github_token(session)
    if not token:
        raise RuntimeError("GitHub credential is not configured")
    await run_git("push", "--set-upstream", "origin", branch_name, cwd=workspace, token=token)
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    if integration is None or integration.encrypted_credentials is None:
        raise RuntimeError("GitHub credential is not configured")
    auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
    client = GitHubClient(auth.token, auth.installation)
    if pull_request_number is None:
        pull_request = await client.find_open_pull_request(
            repository.owner, repository.name, branch_name
        )
        if pull_request is None:
            pull_request = await client.create_pull_request(
                repository.owner,
                repository.name,
                branch_name,
                repository.default_branch,
                task.title,
                task.description or "Automated implementation prepared by Engineering Worker.",
            )
            event_type = "PULL_REQUEST_CREATED"
        else:
            event_type = "PULL_REQUEST_RECOVERED"
        if scope:
            scope.pull_request_number = pull_request.number
            scope.pull_request_url = pull_request.url
        if scope is None or scope.is_primary:
            task.pull_request_number = pull_request.number
            task.pull_request_url = pull_request.url
        await session.commit()
    else:
        pull_request = await client.get_pull_request(
            repository.owner, repository.name, pull_request_number
        )
        event_type = "PULL_REQUEST_UPDATED"
    if scope:
        scope.current_revision = pull_request.head_sha
    if scope is None or scope.is_primary:
        task.current_revision = pull_request.head_sha
    task.state = TaskState.WAITING_GITHUB
    await record_event(
        session,
        task.id,
        event_type,
        {
            "repository_id": str(repository.id),
            "repository": f"{repository.owner}/{repository.name}",
            "number": pull_request.number,
            "url": pull_request.url,
            "head_sha": pull_request.head_sha,
        },
    )
    await session.commit()
    await sync_published_task_to_linear(session, task)
    return pull_request
