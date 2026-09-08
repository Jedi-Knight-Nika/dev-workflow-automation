import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.agent_runtime.application.discover_provider_catalog import DiscoverProviderCatalog
from app.agent_runtime.application.ports.provider_catalog import (
    ProviderCatalogWorkflow,
    ProviderNotConfigured,
    ProviderNotSupported,
)
from app.bootstrap.dependencies import (
    get_github_installation_workflow,
    get_integration_discovery_workflow,
    get_integration_management_workflow,
    get_operations_queries,
    get_provider_catalog_workflow,
    get_repository_management_workflow,
    get_worker_queries,
)
from app.interfaces.http.schemas.dashboard import DashboardActivityRead
from app.interfaces.http.schemas.integrations import (
    DiscoveredRepository,
    IntegrationRead,
    IntegrationUpdate,
    LinearMemberRead,
    LinearWorkflowStateRead,
    ProviderCatalogRead,
    ProviderModelRead,
    RepositoryBatchImport,
    RepositoryCreate,
    RepositoryDependenciesRead,
    RepositoryRead,
    TrelloBoardRead,
    TrelloListRead,
    WebhookHealthRead,
)
from app.interfaces.http.schemas.workers import WorkerNodeRead
from app.platform.configuration.settings import Settings, get_settings
from app.platform.integrations.application.discover_integrations import DiscoverIntegrations
from app.platform.integrations.application.manage_github_installation import (
    ManageGitHubInstallation,
)
from app.platform.integrations.application.manage_integrations import ManageIntegrations
from app.platform.integrations.application.ports.github_installation import (
    GitHubAppSlugInvalid,
    GitHubInstallationNotConfigured,
    GitHubInstallationStateInvalid,
    GitHubInstallationWorkflow,
)
from app.platform.integrations.application.ports.integration_discovery import (
    IntegrationDiscoveryWorkflow,
    IntegrationNotConfigured,
)
from app.platform.integrations.application.ports.integration_management import (
    ConfigureIntegrationCommand,
    IntegrationManagementWorkflow,
    ManagedIntegrationNotConfigured,
)
from app.platform.scheduling.operations import QueryOperations
from app.platform.scheduling.ports.operations_queries import OperationsQueries
from app.platform.scheduling.ports.worker_queries import WorkerQueries
from app.platform.scheduling.query_workers import QueryWorkers
from app.repositories.application.manage_repositories import ManageRepositories
from app.repositories.application.ports.repository_management import (
    CreateRepositoryCommand,
    ManagedRepositoryConflict,
    ManagedRepositoryNotFound,
    RepositoryManagementWorkflow,
)

router = APIRouter(tags=["control-plane"])


@router.get("/activity", response_model=DashboardActivityRead)
async def dashboard_activity(
    queries: OperationsQueries = Depends(get_operations_queries),
) -> DashboardActivityRead:
    activity = await QueryOperations(queries).activity()
    return DashboardActivityRead.model_validate(
        {"active_job": activity.active_job, "queued_jobs": activity.queued_jobs}
    )


@router.get("/webhook-health", response_model=list[WebhookHealthRead])
async def webhook_health(
    queries: OperationsQueries = Depends(get_operations_queries),
) -> list[WebhookHealthRead]:
    health = await QueryOperations(queries).webhook_health()
    return [WebhookHealthRead.model_validate(item, from_attributes=True) for item in health]


@router.get("/providers/{provider_name}/catalog", response_model=ProviderCatalogRead)
async def provider_catalog(
    provider_name: str,
    workflow: ProviderCatalogWorkflow = Depends(get_provider_catalog_workflow),
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
        models=[
            ProviderModelRead(id=model.id, display_name=model.display_name)
            for model in catalog.models
        ],
    )


@router.get("/workers", response_model=list[WorkerNodeRead])
async def list_workers(
    queries: WorkerQueries = Depends(get_worker_queries),
    settings: Settings = Depends(get_settings),
) -> list[WorkerNodeRead]:
    workers = await QueryWorkers(queries, settings.worker_heartbeat_seconds).execute()
    return [WorkerNodeRead.model_validate(worker, from_attributes=True) for worker in workers]


@router.get("/github/repositories", response_model=list[DiscoveredRepository])
async def discover_github_repositories(
    workflow: IntegrationDiscoveryWorkflow = Depends(get_integration_discovery_workflow),
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
    workflow: GitHubInstallationWorkflow = Depends(get_github_installation_workflow),
) -> dict[str, str]:
    try:
        url = await ManageGitHubInstallation(workflow).install_url()
    except GitHubInstallationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GitHubAppSlugInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"url": url}


@router.get("/github/app/manage-url")
async def github_manage_url(
    workflow: GitHubInstallationWorkflow = Depends(get_github_installation_workflow),
) -> dict[str, str]:
    try:
        url = await ManageGitHubInstallation(workflow).manage_url()
    except GitHubInstallationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"url": url}


@router.get("/github/app/account")
async def github_installation_account(
    workflow: GitHubInstallationWorkflow = Depends(get_github_installation_workflow),
) -> dict[str, str]:
    try:
        account = await ManageGitHubInstallation(workflow).account()
    except GitHubInstallationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "login": account.login,
        "account_type": account.account_type,
        "avatar_url": account.avatar_url,
        "profile_url": account.profile_url,
    }


@router.get("/github/app/callback", response_model=None)
async def github_install_callback(
    installation_id: str = Query(min_length=1, pattern=r"^[0-9]+$"),
    state: str = Query(min_length=1),
    workflow: GitHubInstallationWorkflow = Depends(get_github_installation_workflow),
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
    workflow: IntegrationDiscoveryWorkflow = Depends(get_integration_discovery_workflow),
) -> list[LinearWorkflowStateRead]:
    try:
        states = await DiscoverIntegrations(workflow).linear_workflow_states()
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [LinearWorkflowStateRead.model_validate(item, from_attributes=True) for item in states]


@router.get("/linear/members", response_model=list[LinearMemberRead])
async def discover_linear_members(
    workflow: IntegrationDiscoveryWorkflow = Depends(get_integration_discovery_workflow),
) -> list[LinearMemberRead]:
    try:
        members = await DiscoverIntegrations(workflow).linear_members()
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [LinearMemberRead.model_validate(item, from_attributes=True) for item in members]


@router.get("/trello/boards", response_model=list[TrelloBoardRead])
async def discover_trello_boards(
    workflow: IntegrationDiscoveryWorkflow = Depends(get_integration_discovery_workflow),
) -> list[TrelloBoardRead]:
    try:
        boards = await DiscoverIntegrations(workflow).trello_boards()
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [TrelloBoardRead.model_validate(item, from_attributes=True) for item in boards]


@router.get("/trello/boards/{board_id}/lists", response_model=list[TrelloListRead])
async def discover_trello_lists(
    board_id: str,
    workflow: IntegrationDiscoveryWorkflow = Depends(get_integration_discovery_workflow),
) -> list[TrelloListRead]:
    try:
        lists = await DiscoverIntegrations(workflow).trello_lists(board_id)
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [TrelloListRead.model_validate(item, from_attributes=True) for item in lists]


@router.get("/integrations", response_model=list[IntegrationRead])
async def list_integrations(
    workflow: IntegrationManagementWorkflow = Depends(get_integration_management_workflow),
) -> list[IntegrationRead]:
    items = await ManageIntegrations(workflow).list()
    return [IntegrationRead.model_validate(item, from_attributes=True) for item in items]


@router.put("/integrations/{provider_name}", response_model=IntegrationRead)
async def configure_integration(
    provider_name: str,
    body: IntegrationUpdate,
    workflow: IntegrationManagementWorkflow = Depends(get_integration_management_workflow),
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
    workflow: IntegrationManagementWorkflow = Depends(get_integration_management_workflow),
) -> IntegrationRead:
    try:
        result = await ManageIntegrations(workflow).verify(provider_name)
    except ManagedIntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IntegrationRead.model_validate(result, from_attributes=True)


@router.post("/integrations/{provider_name}/sync", response_model=IntegrationRead)
async def request_integration_sync(
    provider_name: str,
    workflow: IntegrationManagementWorkflow = Depends(get_integration_management_workflow),
) -> IntegrationRead:
    try:
        result = await ManageIntegrations(workflow).request_sync(provider_name)
    except ManagedIntegrationNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IntegrationRead.model_validate(result, from_attributes=True)


@router.get("/repositories", response_model=list[RepositoryRead])
async def list_repositories(
    include_archived: bool = False,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> list[RepositoryRead]:
    return [
        RepositoryRead.model_validate(item, from_attributes=True)
        for item in await ManageRepositories(workflow).list(include_archived)
    ]


@router.post("/repositories", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def create_repository(
    body: RepositoryCreate,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryRead:
    command = CreateRepositoryCommand(**body.model_dump())
    try:
        item = await ManageRepositories(workflow).create(command)
    except ManagedRepositoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RepositoryRead.model_validate(item, from_attributes=True)


@router.post("/repositories/import", response_model=list[RepositoryRead])
async def import_repositories(
    body: RepositoryBatchImport,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> list[RepositoryRead]:
    commands = [CreateRepositoryCommand(**item.model_dump()) for item in body.repositories]
    try:
        items = await ManageRepositories(workflow).import_batch(commands)
    except ManagedRepositoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [RepositoryRead.model_validate(item, from_attributes=True) for item in items]


@router.patch("/repositories/{repository_id}/enabled", response_model=RepositoryRead)
async def set_repository_enabled(
    repository_id: uuid.UUID,
    enabled: bool,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryRead:
    try:
        result = await ManageRepositories(workflow).set_enabled(repository_id, enabled)
    except ManagedRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ManagedRepositoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RepositoryRead.model_validate(result, from_attributes=True)


@router.patch("/repositories/{repository_id}/archived", response_model=RepositoryRead)
async def set_repository_archived(
    repository_id: uuid.UUID,
    archived: bool,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryRead:
    try:
        result = await ManageRepositories(workflow).set_archived(repository_id, archived)
    except ManagedRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RepositoryRead.model_validate(result, from_attributes=True)


@router.get("/repositories/{repository_id}/dependencies", response_model=RepositoryDependenciesRead)
async def repository_dependencies(
    repository_id: uuid.UUID,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryDependenciesRead:
    try:
        result = await ManageRepositories(workflow).dependencies(repository_id)
    except ManagedRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RepositoryDependenciesRead.model_validate(result, from_attributes=True)


@router.delete("/repositories/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: uuid.UUID,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> None:
    try:
        await ManageRepositories(workflow).delete(repository_id)
    except ManagedRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ManagedRepositoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
