import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.catalog_factory import create_provider
from app.delivery.infrastructure.github_client import GitHubClient
from app.engineering.domain.lifecycle import TaskStatus
from app.engineering.infrastructure.task_models import Job, Task
from app.intake.infrastructure.linear_client import LinearClient
from app.intake.infrastructure.task_snapshot import ExternalTaskSnapshot
from app.intake.infrastructure.trello_client import TrelloClient
from app.platform.integrations.application.ports.integration_management import (
    ConfigureIntegrationCommand,
    IntegrationView,
    ManagedIntegrationNotConfigured,
)
from app.platform.integrations.github_auth import resolve_github_auth
from app.platform.integrations.infrastructure.errors import connection_error
from app.platform.integrations.models import Integration
from app.platform.scheduling.states import IntegrationStatus, JobState
from app.platform.security.crypto import cipher
from app.repositories.infrastructure.models import Repository
from app.teams.infrastructure.models import TeamAgentProfile
from app.teams.infrastructure.team_models import Team


def integration_display_status(item: Integration) -> str:
    if item.status is IntegrationStatus.CONNECTED:
        return "WORKING" if item.sync_status in {"QUEUED", "RUNNING"} else "READY"
    if item.status is IntegrationStatus.ERROR or item.sync_status == "FAILED":
        return "NEEDS_ATTENTION"
    if item.status is IntegrationStatus.DISCONNECTED:
        return "NOT_CONFIGURED"
    return "WORKING"


def integration_to_view(item: Integration, usage: dict[str, int] | None = None) -> IntegrationView:
    return IntegrationView(
        item.id,
        item.provider_type,
        item.provider_name,
        item.status.value,
        item.configuration,
        item.encrypted_credentials is not None,
        item.last_error,
        item.sync_status,
        item.last_synced_at,
        item.updated_at,
        integration_display_status(item),
        usage or {},
    )


class EncryptedIntegrationManagementWorkflow:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get(self, name: str) -> Integration | None:
        result: Integration | None = await self._session.scalar(
            select(Integration).where(Integration.provider_name == name)
        )
        return result

    async def list(self) -> list[IntegrationView]:
        items = list(
            await self._session.scalars(select(Integration).order_by(Integration.provider_name))
        )
        agent_rows = (
            await self._session.execute(
                select(
                    TeamAgentProfile.provider,
                    func.count(TeamAgentProfile.id).label("agents_count"),
                    func.count(func.distinct(TeamAgentProfile.team_id)).label("teams_count"),
                ).group_by(TeamAgentProfile.provider)
            )
        ).mappings()
        agent_usage = {
            str(row["provider"]): (int(row["agents_count"]), int(row["teams_count"]))
            for row in agent_rows
            if row["provider"]
        }
        repository_rows = (
            await self._session.execute(
                select(Repository.provider, func.count(Repository.id).label("count"))
                .where(Repository.archived_at.is_(None))
                .group_by(Repository.provider)
            )
        ).mappings()
        repository_counts = {str(row["provider"]): int(row["count"]) for row in repository_rows}
        active_states = {TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.MERGED}
        source_rows = (
            await self._session.execute(
                select(
                    ExternalTaskSnapshot.provider,
                    func.count(func.distinct(Task.id)).label("active_tasks"),
                    func.count(func.distinct(Task.team_id)).label("teams_count"),
                )
                .join(Task, Task.id == ExternalTaskSnapshot.task_id)
                .where(Task.archived_at.is_(None), Task.status.not_in(active_states))
                .group_by(ExternalTaskSnapshot.provider)
            )
        ).mappings()
        source_usage = {
            str(row["provider"]): (int(row["active_tasks"]), int(row["teams_count"]))
            for row in source_rows
        }
        waiting_rows = (
            await self._session.execute(
                select(TeamAgentProfile.provider, func.count(Job.id).label("count"))
                .join(Task, Task.id == Job.task_id)
                .join(
                    TeamAgentProfile,
                    (TeamAgentProfile.team_id == Task.team_id)
                    & (TeamAgentProfile.role_kind == "DEVELOPER"),
                )
                .where(
                    Job.state.in_(
                        {
                            JobState.WAITING_PROVIDER,
                            JobState.WAITING_INTEGRATION,
                            JobState.WAITING_CONFIGURATION,
                        }
                    )
                )
                .group_by(TeamAgentProfile.provider)
            )
        ).mappings()
        waiting_counts = {
            str(row["provider"]): int(row["count"]) for row in waiting_rows if row["provider"]
        }
        teams = list((await self._session.scalars(select(Team))).all())
        repository_ids_by_provider: dict[str, set[str]] = {}
        for repository in (
            await self._session.scalars(select(Repository).where(Repository.archived_at.is_(None)))
        ).all():
            repository_ids_by_provider.setdefault(repository.provider, set()).add(
                str(repository.id)
            )
        views: list[IntegrationView] = []
        for item in items:
            agents_count, agent_teams = agent_usage.get(item.provider_name, (0, 0))
            active_tasks, source_teams = source_usage.get(item.provider_name, (0, 0))
            repository_ids = repository_ids_by_provider.get(item.provider_name, set())
            repository_teams = sum(
                1 for team in teams if repository_ids.intersection(team.repository_ids or [])
            )
            usage = {
                "agents_count": agents_count,
                "teams_count": max(agent_teams, source_teams, repository_teams),
                "repositories_count": repository_counts.get(item.provider_name, 0),
                "active_tasks_count": active_tasks,
                "waiting_jobs_count": waiting_counts.get(item.provider_name, 0),
            }
            views.append(integration_to_view(item, usage))
        return views

    async def configure(self, command: ConfigureIntegrationCommand) -> IntegrationView:
        item = await self._get(command.provider_name)
        if item is None:
            item = Integration(
                provider_name=command.provider_name, provider_type=command.provider_type
            )
            self._session.add(item)
        item.provider_type = command.provider_type
        item.status = IntegrationStatus(command.status)
        item.configuration = command.configuration
        if command.credential is not None:
            item.encrypted_credentials = cipher.encrypt(command.credential)
        item.last_error = None
        await self._session.commit()
        await self._session.refresh(item)
        return integration_to_view(item)

    async def verify(self, provider_name: str) -> IntegrationView:
        item = await self._get(provider_name)
        if item is None or item.encrypted_credentials is None:
            raise ManagedIntegrationNotConfigured("Configure credentials first")
        credential = cipher.decrypt(item.encrypted_credentials)
        try:
            if provider_name == "github":
                auth = await resolve_github_auth(credential)
                await GitHubClient(auth.token, auth.installation).list_repositories()
            elif provider_name == "linear":
                await LinearClient(credential).list_workflow_states()
            elif provider_name == "trello":
                await TrelloClient(credential).list_boards()
            elif provider_name in {"openai", "anthropic", "deepseek"}:
                await create_provider(provider_name, credential).list_models()
            else:
                raise ValueError(f"Unsupported integration: {provider_name}")
        except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
            item.status, item.last_error = (
                IntegrationStatus.ERROR,
                connection_error(provider_name, exc),
            )
        else:
            item.status, item.last_error = IntegrationStatus.CONNECTED, None
        await self._session.commit()
        return integration_to_view(item)

    async def request_sync(self, provider_name: str) -> IntegrationView:
        item = await self._get(provider_name)
        if item is None or item.encrypted_credentials is None:
            raise ManagedIntegrationNotConfigured("Configure credentials first")
        if provider_name not in {"linear", "trello"}:
            raise ManagedIntegrationNotConfigured("This integration does not synchronize tasks")
        item.sync_status = "QUEUED"
        item.last_synced_at = None
        await self._session.commit()
        return integration_to_view(item)
