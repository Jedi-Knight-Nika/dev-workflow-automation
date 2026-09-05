import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.application.discover_integrations import DiscoverIntegrations
from app.application.discover_provider_catalog import DiscoverProviderCatalog
from app.application.manage_agents import ManageAgents
from app.application.manage_integrations import ManageIntegrations
from app.application.manage_repositories import ManageRepositories
from app.application.operations import QueryOperations
from app.application.ports.agent_configuration import AgentConfigCommand
from app.application.ports.integration_discovery import IntegrationNotConfigured
from app.application.ports.integration_management import (
    ConfigureIntegrationCommand,
    ManagedIntegrationNotConfigured,
)
from app.application.ports.knowledge_search import SearchIndexNotReady, SearchRepositoryNotFound
from app.application.ports.provider_catalog import ProviderNotConfigured, ProviderNotSupported
from app.application.ports.repository_management import (
    CreateRepositoryCommand,
    ManagedRepositoryConflict,
    ManagedRepositoryNotFound,
)
from app.application.query_workers import QueryWorkers
from app.application.search_knowledge import SearchKnowledge
from app.bootstrap.dependencies import (
    get_agent_configuration_workflow,
    get_github_installation_workflow,
    get_integration_discovery_workflow,
    get_integration_management_workflow,
    get_knowledge_search_workflow,
    get_operations_queries,
    get_provider_catalog_workflow,
    get_repository_management_workflow,
    get_worker_queries,
)
from app.config import Settings, get_settings
from app.domain.agents import AgentRole
from app.infrastructure.github_installation import EncryptedGitHubInstallationWorkflow
from app.infrastructure.integration_discovery import EncryptedIntegrationDiscoveryWorkflow
from app.infrastructure.integration_management import EncryptedIntegrationManagementWorkflow
from app.infrastructure.knowledge_search import SqlAlchemyKnowledgeSearchWorkflow
from app.infrastructure.persistence.agent_configuration import SqlAlchemyAgentConfigurationWorkflow
from app.infrastructure.persistence.operations_queries import SqlAlchemyOperationsQueries
from app.infrastructure.persistence.repository_management import (
    SqlAlchemyRepositoryManagementWorkflow,
)
from app.infrastructure.persistence.worker_queries import SqlAlchemyWorkerQueries
from app.infrastructure.providers import EncryptedProviderCatalogWorkflow
from app.schemas import (
    AgentConfigRead,
    AgentConfigUpdate,
    DashboardActivityRead,
    DiscoveredRepository,
    IntegrationRead,
    IntegrationUpdate,
    KnowledgeSearchResult,
    LinearWorkflowStateRead,
    ProviderCatalogRead,
    RepositoryCreate,
    RepositoryRead,
    WebhookHealthRead,
    WorkerNodeRead,
)

router = APIRouter(tags=["control-plane"])


@router.get("/activity", response_model=DashboardActivityRead)
async def dashboard_activity(
    queries: SqlAlchemyOperationsQueries = Depends(get_operations_queries),
) -> DashboardActivityRead:
    activity = await QueryOperations(queries).activity()
    return DashboardActivityRead.model_validate(
        {"active_job": activity.active_job, "queued_jobs": activity.queued_jobs}
    )


@router.get("/webhook-health", response_model=list[WebhookHealthRead])
async def webhook_health(
    queries: SqlAlchemyOperationsQueries = Depends(get_operations_queries),
) -> list[WebhookHealthRead]:
    health = await QueryOperations(queries).webhook_health()
    return [WebhookHealthRead.model_validate(item, from_attributes=True) for item in health]


@router.get("/providers/{provider_name}/catalog", response_model=ProviderCatalogRead)
async def provider_catalog(
    provider_name: str,
    workflow: EncryptedProviderCatalogWorkflow = Depends(get_provider_catalog_workflow),
) -> ProviderCatalogRead:
    try:
        catalog = await DiscoverProviderCatalog(workflow).execute(provider_name)
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProviderNotSupported as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProviderCatalogRead(
        provider=catalog.provider,
        capabilities=catalog.capabilities,
        models=[{"id": model.id, "display_name": model.display_name} for model in catalog.models],
    )


@router.get("/workers", response_model=list[WorkerNodeRead])
async def list_workers(
    queries: SqlAlchemyWorkerQueries = Depends(get_worker_queries),
    settings: Settings = Depends(get_settings),
) -> list[WorkerNodeRead]:
    workers = await QueryWorkers(queries, settings.worker_heartbeat_seconds).execute()
    return [WorkerNodeRead.model_validate(worker, from_attributes=True) for worker in workers]


@router.get("/github/repositories", response_model=list[DiscoveredRepository])
async def discover_github_repositories(
    workflow: EncryptedIntegrationDiscoveryWorkflow = Depends(get_integration_discovery_workflow),
) -> list[DiscoveredRepository]:
    try:
        repositories = await DiscoverIntegrations(workflow).github_repositories()
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [
        DiscoveredRepository.model_validate(item, from_attributes=True) for item in repositories
    ]


@router.get("/github/app/install-url")
async def github_install_url(
    workflow: EncryptedGitHubInstallationWorkflow = Depends(get_github_installation_workflow),
) -> dict[str, str]:
    try:
        url = await ManageGitHubInstallation(workflow).install_url()
    except GitHubInstallationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GitHubAppSlugInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"url": url}


@router.get("/github/app/callback", response_model=None)
async def github_install_callback(
    installation_id: str = Query(min_length=1, pattern=r"^[0-9]+$"),
    state: str = Query(min_length=1),
    workflow: EncryptedGitHubInstallationWorkflow = Depends(get_github_installation_workflow),
) -> RedirectResponse:
    try:
        result = await ManageGitHubInstallation(workflow).complete(installation_id, state)
    except GitHubInstallationStateInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubInstallationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(result.redirect_url, status_code=303)


@router.get("/linear/workflow-states", response_model=list[LinearWorkflowStateRead])
async def discover_linear_workflow_states(
    workflow: EncryptedIntegrationDiscoveryWorkflow = Depends(get_integration_discovery_workflow),
) -> list[LinearWorkflowStateRead]:
    try:
        states = await DiscoverIntegrations(workflow).linear_workflow_states()
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [LinearWorkflowStateRead.model_validate(item, from_attributes=True) for item in states]


@router.get("/integrations", response_model=list[IntegrationRead])
async def list_integrations(
    workflow: EncryptedIntegrationManagementWorkflow = Depends(get_integration_management_workflow),
) -> list[IntegrationRead]:
    items = await ManageIntegrations(workflow).list()
    return [IntegrationRead.model_validate(item, from_attributes=True) for item in items]


@router.put("/integrations/{provider_name}", response_model=IntegrationRead)
async def configure_integration(
    provider_name: str,
    body: IntegrationUpdate,
    workflow: EncryptedIntegrationManagementWorkflow = Depends(get_integration_management_workflow),
) -> IntegrationRead:
    command = ConfigureIntegrationCommand(
        provider_name,
        body.provider_type,
        body.status.value,
        body.configuration,
        body.credential.get_secret_value() if body.credential else None,
    )
    return IntegrationRead.model_validate(
        await ManageIntegrations(workflow).configure(command), from_attributes=True
    )


@router.post("/integrations/{provider_name}/test", response_model=IntegrationRead)
async def test_integration(
    provider_name: str,
    workflow: EncryptedIntegrationManagementWorkflow = Depends(get_integration_management_workflow),
) -> IntegrationRead:
    try:
        result = await ManageIntegrations(workflow).verify(provider_name)
    except ManagedIntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IntegrationRead.model_validate(result, from_attributes=True)


@router.get("/repositories", response_model=list[RepositoryRead])
async def list_repositories(
    workflow: SqlAlchemyRepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> list[RepositoryRead]:
    return [
        RepositoryRead.model_validate(item, from_attributes=True)
        for item in await ManageRepositories(workflow).list()
    ]


@router.post("/repositories", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def create_repository(
    body: RepositoryCreate,
    workflow: SqlAlchemyRepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryRead:
    command = CreateRepositoryCommand(**body.model_dump())
    return RepositoryRead.model_validate(
        await ManageRepositories(workflow).create(command), from_attributes=True
    )


@router.patch("/repositories/{repository_id}/enabled", response_model=RepositoryRead)
async def set_repository_enabled(
    repository_id: uuid.UUID,
    enabled: bool,
    workflow: SqlAlchemyRepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryRead:
    try:
        result = await ManageRepositories(workflow).set_enabled(repository_id, enabled)
    except ManagedRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RepositoryRead.model_validate(result, from_attributes=True)


@router.post("/repositories/{repository_id}/index", response_model=RepositoryRead)
async def queue_repository_index(
    repository_id: uuid.UUID,
    workflow: SqlAlchemyRepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryRead:
    try:
        result = await ManageRepositories(workflow).queue_index(repository_id)
    except ManagedRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ManagedRepositoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RepositoryRead.model_validate(result, from_attributes=True)


@router.get("/repositories/{repository_id}/search", response_model=list[KnowledgeSearchResult])
async def search_repository_knowledge(
    repository_id: uuid.UUID,
    query: str,
    limit: int = 8,
    workflow: SqlAlchemyKnowledgeSearchWorkflow = Depends(get_knowledge_search_workflow),
) -> list[KnowledgeSearchResult]:
    try:
        results = await SearchKnowledge(workflow).execute(repository_id, query, limit)
    except SearchRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SearchIndexNotReady as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [KnowledgeSearchResult.model_validate(item, from_attributes=True) for item in results]


@router.get("/agents", response_model=list[AgentConfigRead])
async def list_agent_configs(
    workflow: SqlAlchemyAgentConfigurationWorkflow = Depends(get_agent_configuration_workflow),
) -> list[AgentConfigRead]:
    return [
        AgentConfigRead.model_validate(item, from_attributes=True)
        for item in await ManageAgents(workflow).list()
    ]


@router.put("/agents/{role}", response_model=AgentConfigRead)
async def update_agent_config(
    role: AgentRole,
    body: AgentConfigUpdate,
    workflow: SqlAlchemyAgentConfigurationWorkflow = Depends(get_agent_configuration_workflow),
) -> AgentConfigRead:
    result = await ManageAgents(workflow).update(
        AgentConfigCommand(role.value, body.enabled, body.provider, body.model, body.configuration)
    )
    return AgentConfigRead.model_validate(result, from_attributes=True)


from app.application.manage_github_installation import ManageGitHubInstallation
from app.application.ports.github_installation import (
    GitHubAppSlugInvalid,
    GitHubInstallationNotConfigured,
    GitHubInstallationStateInvalid,
)
