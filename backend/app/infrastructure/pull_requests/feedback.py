from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Integration, Repository, Task
from app.infrastructure.integration_access import role_allows_integration
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth


async def latest_github_pull_request_feedback(
    session: AsyncSession, task: Task
) -> dict[str, object] | None:
    if task.repository_id is None or task.pull_request_number is None:
        return None
    repository = await session.get(Repository, task.repository_id)
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    if (
        repository is None
        or integration is None
        or integration.encrypted_credentials is None
        or not await role_allows_integration(session, "DELIVERER", integration.id)
    ):
        return None
    try:
        auth = await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))
        feedback = await GitHubClient(auth.token, auth.installation).latest_pull_request_feedback(
            repository.owner, repository.name, task.pull_request_number
        )
    except Exception:  # noqa: BLE001 - persisted webhook history remains the safe fallback
        return None
    if feedback is None:
        return None
    return {
        "source": "github",
        "event_type": "pull_request_feedback_refresh",
        "author": feedback["author"],
        "url": feedback["url"],
        "raw_text": feedback["raw_text"],
        "previous_state": "NEW",
        "refreshed_after_manual_reopen": True,
    }
