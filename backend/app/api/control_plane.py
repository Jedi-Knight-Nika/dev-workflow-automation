import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.application.design_workflow import DesignWorkflow
from app.application.discover_integrations import DiscoverIntegrations
from app.application.discover_provider_catalog import DiscoverProviderCatalog
from app.application.manage_agent_knowledge import ManageAgentKnowledge
from app.application.manage_agents import ManageAgents
from app.application.manage_integrations import ManageIntegrations
from app.application.manage_repositories import ManageRepositories
from app.application.operations import QueryOperations
from app.application.ports.agent_configuration import AgentConfigCommand, AgentConfigurationWorkflow
from app.application.ports.agent_knowledge import AgentKnowledgeWorkflow
from app.application.ports.github_installation import GitHubInstallationWorkflow
from app.application.ports.integration_discovery import (
    IntegrationDiscoveryWorkflow,
    IntegrationNotConfigured,
)
from app.application.ports.integration_management import (
    ConfigureIntegrationCommand,
    IntegrationManagementWorkflow,
    ManagedIntegrationNotConfigured,
)
from app.application.ports.knowledge_search import (
    KnowledgeSearchWorkflow,
    SearchIndexNotReady,
    SearchRepositoryNotFound,
)
from app.application.ports.model_validation import ModelValidationGateway, NodeModelValidationStore
from app.application.ports.operations_queries import OperationsQueries
from app.application.ports.provider_catalog import (
    ProviderCatalogWorkflow,
    ProviderNotConfigured,
    ProviderNotSupported,
)
from app.application.ports.repository_management import (
    CreateRepositoryCommand,
    ManagedRepositoryConflict,
    ManagedRepositoryNotFound,
    RepositoryManagementWorkflow,
)
from app.application.ports.worker_queries import WorkerQueries
from app.application.ports.workflow_designer import WorkflowDesigner, WorkflowVersionConflict
from app.application.query_workers import QueryWorkers
from app.application.search_knowledge import SearchKnowledge
from app.application.validate_node_model import ValidateNodeModel
from app.bootstrap.dependencies import (
    get_agent_configuration_workflow,
    get_agent_knowledge_workflow,
    get_github_installation_workflow,
    get_integration_discovery_workflow,
    get_integration_management_workflow,
    get_knowledge_search_workflow,
    get_operations_queries,
    get_provider_catalog_workflow,
    get_repository_management_workflow,
    get_worker_queries,
    get_workflow_designer,
)
from app.config import Settings, get_settings
from app.domain.agents import AgentRole
from app.domain.workflows import WorkflowEdgeData, WorkflowGraphData, WorkflowNodeData
from app.schemas import (
    AgentConfigRead,
    AgentConfigUpdate,
    AgentKnowledgeCreate,
    AgentKnowledgeRead,
    DashboardActivityRead,
    DiscoveredRepository,
    IntegrationRead,
    IntegrationUpdate,
    KnowledgeSearchResult,
    LinearMemberRead,
    LinearWorkflowStateRead,
    ProviderCatalogRead,
    RepositoryCreate,
    RepositoryRead,
    WebhookHealthRead,
    WorkerNodeRead,
    WorkflowGraphRead,
    WorkflowNodeModelValidationRead,
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
        models=[{"id": model.id, "display_name": model.display_name} for model in catalog.models],
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


@router.get("/repositories", response_model=list[RepositoryRead])
async def list_repositories(
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> list[RepositoryRead]:
    return [
        RepositoryRead.model_validate(item, from_attributes=True)
        for item in await ManageRepositories(workflow).list()
    ]


@router.post("/repositories", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def create_repository(
    body: RepositoryCreate,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryRead:
    command = CreateRepositoryCommand(**body.model_dump())
    return RepositoryRead.model_validate(
        await ManageRepositories(workflow).create(command), from_attributes=True
    )


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
    return RepositoryRead.model_validate(result, from_attributes=True)


@router.post("/repositories/{repository_id}/index", response_model=RepositoryRead)
async def queue_repository_index(
    repository_id: uuid.UUID,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> RepositoryRead:
    try:
        result = await ManageRepositories(workflow).queue_index(repository_id)
    except ManagedRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ManagedRepositoryConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RepositoryRead.model_validate(result, from_attributes=True)


@router.delete("/repositories/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: uuid.UUID,
    workflow: RepositoryManagementWorkflow = Depends(get_repository_management_workflow),
) -> None:
    try:
        await ManageRepositories(workflow).delete(repository_id)
    except ManagedRepositoryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/repositories/{repository_id}/search", response_model=list[KnowledgeSearchResult])
async def search_repository_knowledge(
    repository_id: uuid.UUID,
    query: str,
    limit: int = 8,
    workflow: KnowledgeSearchWorkflow = Depends(get_knowledge_search_workflow),
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
    workflow: AgentConfigurationWorkflow = Depends(get_agent_configuration_workflow),
) -> list[AgentConfigRead]:
    return [
        AgentConfigRead.model_validate(item, from_attributes=True)
        for item in await ManageAgents(workflow).list()
    ]


@router.put("/agents/{role}", response_model=AgentConfigRead)
async def update_agent_config(
    role: AgentRole,
    body: AgentConfigUpdate,
    workflow: AgentConfigurationWorkflow = Depends(get_agent_configuration_workflow),
) -> AgentConfigRead:
    result = await ManageAgents(workflow).update(
        AgentConfigCommand(role.value, body.enabled, body.provider, body.model, body.configuration)
    )
    return AgentConfigRead.model_validate(result, from_attributes=True)


@router.get("/agents/{role}/knowledge", response_model=list[AgentKnowledgeRead])
async def list_role_knowledge(
    role: AgentRole, workflow: AgentKnowledgeWorkflow = Depends(get_agent_knowledge_workflow)
) -> list[AgentKnowledgeRead]:
    return [
        AgentKnowledgeRead.model_validate(item, from_attributes=True)
        for item in await ManageAgentKnowledge(workflow).list(role.value)
    ]


@router.post("/agents/{role}/knowledge", response_model=AgentKnowledgeRead, status_code=201)
async def add_role_knowledge(
    role: AgentRole,
    body: AgentKnowledgeCreate,
    workflow: AgentKnowledgeWorkflow = Depends(get_agent_knowledge_workflow),
) -> AgentKnowledgeRead:
    try:
        result = await ManageAgentKnowledge(workflow).create(role.value, body.title, body.content)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return AgentKnowledgeRead.model_validate(result, from_attributes=True)


@router.delete("/agents/{role}/knowledge/{source_id}", status_code=204)
async def remove_role_knowledge(
    role: AgentRole,
    source_id: uuid.UUID,
    workflow: AgentKnowledgeWorkflow = Depends(get_agent_knowledge_workflow),
) -> None:
    if not await ManageAgentKnowledge(workflow).delete(role.value, source_id):
        raise HTTPException(status_code=404, detail="Agent knowledge source not found")


def workflow_response(graph: WorkflowGraphData) -> WorkflowGraphRead:
    return WorkflowGraphRead.model_validate(
        {
            "version": graph.version,
            "nodes": [asdict(node) for node in graph.nodes],
            "edges": [asdict(edge) for edge in graph.edges],
        }
    )


@router.get("/workflow", response_model=WorkflowGraphRead)
async def get_workflow(
    designer: WorkflowDesigner = Depends(get_workflow_designer),
) -> WorkflowGraphRead:
    return workflow_response(await DesignWorkflow(designer).get())


@router.put("/workflow", response_model=WorkflowGraphRead)
async def replace_workflow(
    body: WorkflowGraphRead,
    designer: WorkflowDesigner = Depends(get_workflow_designer),
) -> WorkflowGraphRead:
    graph = WorkflowGraphData(
        body.version,
        tuple(
            WorkflowNodeData(
                str(node.id),
                node.role,
                node.label,
                node.position_x,
                node.position_y,
                node.enabled,
                node.activation_policy,
                node.batch_window_seconds,
                tuple(str(item) for item in node.integration_ids),
                tuple(str(item) for item in node.repository_ids),
                node.provider,
                node.model,
                node.system_prompt,
                node.model_validation_status,
                node.model_validation_message,
                node.model_validated_at,
                node.integration_mode,
                node.poll_interval_seconds,
                node.filter_assignee_id,
                tuple(node.filter_state_ids),
                node.integration_sync_status,
                node.integration_sync_error,
                node.integration_last_synced_at,
                node.reasoning_effort,
                node.max_output_tokens,
                node.temperature,
                node.timeout_minutes,
                node.max_retries,
                node.max_review_cycles,
                node.context_depth,
                node.rag_retrieval_depth,
                node.fallback_provider,
                node.fallback_model,
                str(node.agent_id) if node.agent_id else None,
            )
            for node in body.nodes
        ),
        tuple(
            WorkflowEdgeData(
                str(edge.id),
                str(edge.source_node_id),
                str(edge.target_node_id),
                edge.outcome,
                edge.required,
            )
            for edge in body.edges
        ),
    )
    try:
        return workflow_response(await DesignWorkflow(designer).replace(graph))
    except WorkflowVersionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/workflow/nodes/{node_id}/validate-model",
    response_model=WorkflowNodeModelValidationRead,
)
async def validate_workflow_node_model(
    node_id: uuid.UUID,
    designer: NodeModelValidationStore = Depends(get_workflow_designer),
    gateway: ModelValidationGateway = Depends(get_provider_catalog_workflow),
) -> WorkflowNodeModelValidationRead:
    try:
        result = await ValidateNodeModel(designer, gateway).execute(str(node_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WorkflowNodeModelValidationRead.model_validate(result, from_attributes=True)


from app.application.manage_github_installation import ManageGitHubInstallation
from app.application.ports.github_installation import (
    GitHubAppSlugInvalid,
    GitHubInstallationNotConfigured,
    GitHubInstallationStateInvalid,
)
