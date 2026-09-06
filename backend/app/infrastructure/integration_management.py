import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.integration_management import (
    ConfigureIntegrationCommand,
    IntegrationView,
    ManagedIntegrationNotConfigured,
)
from app.db.models import (
    AIAgent,
    ExternalTaskSnapshot,
    Integration,
    IntegrationStatus,
    Job,
    JobState,
    Repository,
    Task,
    Team,
    WorkflowNode,
)
from app.domain.tasks import TaskState
from app.infrastructure.security.crypto import cipher
from app.integrations.github import GitHubClient
from app.integrations.github_auth import resolve_github_auth
from app.integrations.linear import LinearClient
from app.integrations.trello import TrelloClient
from app.providers import create_provider


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
        nodes = list((await self._session.scalars(select(WorkflowNode))).all())
        agent_rows = (
            await self._session.execute(
                select(
                    AIAgent.provider,
                    func.count(AIAgent.id).label("agents_count"),
                    func.count(func.distinct(AIAgent.team_id)).label("teams_count"),
                ).group_by(AIAgent.provider)
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
        active_states = {TaskState.CANCELLED, TaskState.FAILED, TaskState.MERGED}
        source_rows = (
            await self._session.execute(
                select(
                    ExternalTaskSnapshot.provider,
                    func.count(func.distinct(Task.id)).label("active_tasks"),
                    func.count(func.distinct(Task.team_id)).label("teams_count"),
                )
                .join(Task, Task.id == ExternalTaskSnapshot.task_id)
                .where(Task.archived_at.is_(None), Task.state.not_in(active_states))
                .group_by(ExternalTaskSnapshot.provider)
            )
        ).mappings()
        source_usage = {
            str(row["provider"]): (int(row["active_tasks"]), int(row["teams_count"]))
            for row in source_rows
        }
        waiting_rows = (
            await self._session.execute(
                select(AIAgent.provider, func.count(Job.id).label("count"))
                .join(AIAgent, AIAgent.id == Job.agent_id)
                .where(
                    Job.state.in_(
                        {
                            JobState.WAITING_PROVIDER,
                            JobState.WAITING_INTEGRATION,
                            JobState.WAITING_CONFIGURATION,
                        }
                    )
                )
                .group_by(AIAgent.provider)
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
                "workflow_nodes_count": sum(
                    str(item.id) in (node.integration_ids or []) for node in nodes
                ),
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
            elif provider_name in {"openai", "anthropic", "google"}:
                await create_provider(provider_name, credential).list_models()
            elif provider_name in {"npm_registry", "pypi_registry"}:
                if not credential.strip():
                    raise ValueError("Registry token cannot be empty")
            else:
                raise ValueError(f"Unsupported integration: {provider_name}")
        except (httpx.HTTPError, RuntimeError, TypeError, ValueError) as exc:
            item.status, item.last_error = IntegrationStatus.ERROR, str(exc)[:2000]
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
        if provider_name == "linear":
            nodes = list(
                (
                    await self._session.scalars(
                        select(WorkflowNode).where(WorkflowNode.role == "INTAKE")
                    )
                ).all()
            )
            for node in nodes:
                if str(item.id) in (node.integration_ids or []):
                    node.integration_last_synced_at = None
                    node.integration_sync_status = "QUEUED"
        await self._session.commit()
        return integration_to_view(item)
