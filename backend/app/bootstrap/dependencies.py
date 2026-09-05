import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.query_events import QueryEvents
from app.config import Settings, get_settings
from app.db.session import SessionLocal, get_session
from app.infrastructure.agent_knowledge import SqlAlchemyAgentKnowledgeWorkflow
from app.infrastructure.github_installation import EncryptedGitHubInstallationWorkflow
from app.infrastructure.integration_discovery import EncryptedIntegrationDiscoveryWorkflow
from app.infrastructure.integration_management import EncryptedIntegrationManagementWorkflow
from app.infrastructure.knowledge_search import SqlAlchemyKnowledgeSearchWorkflow
from app.infrastructure.persistence import SqlAlchemyUnitOfWork
from app.infrastructure.persistence.agent_configuration import SqlAlchemyAgentConfigurationWorkflow
from app.infrastructure.persistence.event_queries import SqlAlchemyEventQueries
from app.infrastructure.persistence.job_enqueueing import SqlAlchemyJobEnqueueWorkflow
from app.infrastructure.persistence.operations_queries import SqlAlchemyOperationsQueries
from app.infrastructure.persistence.readiness import SqlAlchemyReadinessProbe
from app.infrastructure.persistence.repository_management import (
    SqlAlchemyRepositoryManagementWorkflow,
)
from app.infrastructure.persistence.role_management import SqlAlchemyRoleManagementWorkflow
from app.infrastructure.persistence.task_history import SqlAlchemyTaskHistoryQueries
from app.infrastructure.persistence.task_lifecycle import SqlAlchemyTaskLifecycleUnitOfWorkFactory
from app.infrastructure.persistence.task_queries import SqlAlchemyTaskQueries
from app.infrastructure.persistence.team_management import SqlAlchemyTeamManagementWorkflow
from app.infrastructure.persistence.terminal_sessions import SqlAlchemyTerminalSessionGateway
from app.infrastructure.persistence.tracker_sync import SqlAlchemyLinearSyncWorkflow
from app.infrastructure.persistence.worker_queries import SqlAlchemyWorkerQueries
from app.infrastructure.persistence.workflow_designer import SqlAlchemyWorkflowDesigner
from app.infrastructure.providers import EncryptedProviderCatalogWorkflow
from app.infrastructure.pull_requests import (
    SqlAlchemyGitHubMergeWorkflow,
    SqlAlchemyGitHubPublicationWorkflow,
)
from app.infrastructure.webhook_ingestion import SqlAlchemyWebhookIngestionWorkflow
from app.infrastructure.workspaces import SqlAlchemyGitWorkspaceWorkflow


def get_unit_of_work(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def get_event_queries() -> QueryEvents:
    return QueryEvents(SqlAlchemyEventQueries(SessionLocal))


def get_readiness_probe(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyReadinessProbe:
    return SqlAlchemyReadinessProbe(session)


def get_merge_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyGitHubMergeWorkflow:
    return SqlAlchemyGitHubMergeWorkflow(session)


def get_pull_request_publication_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyGitHubPublicationWorkflow:
    return SqlAlchemyGitHubPublicationWorkflow(session)


def get_task_lifecycle_factory() -> SqlAlchemyTaskLifecycleUnitOfWorkFactory:
    return SqlAlchemyTaskLifecycleUnitOfWorkFactory(SessionLocal)


def get_workspace_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyGitWorkspaceWorkflow:
    return SqlAlchemyGitWorkspaceWorkflow(session)


def get_job_enqueue_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyJobEnqueueWorkflow:
    return SqlAlchemyJobEnqueueWorkflow(session)


def get_tracker_sync_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyLinearSyncWorkflow:
    return SqlAlchemyLinearSyncWorkflow(session)


def get_task_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyTaskQueries:
    return SqlAlchemyTaskQueries(session)


def get_task_history_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyTaskHistoryQueries:
    return SqlAlchemyTaskHistoryQueries(session)


def get_operations_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyOperationsQueries:
    return SqlAlchemyOperationsQueries(session)


def get_provider_catalog_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EncryptedProviderCatalogWorkflow:
    return EncryptedProviderCatalogWorkflow(session)


def get_worker_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyWorkerQueries:
    return SqlAlchemyWorkerQueries(session)


def get_agent_configuration_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyAgentConfigurationWorkflow:
    return SqlAlchemyAgentConfigurationWorkflow(session)


def get_agent_knowledge_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyAgentKnowledgeWorkflow:
    return SqlAlchemyAgentKnowledgeWorkflow(session)


def get_workflow_designer(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyWorkflowDesigner:
    return SqlAlchemyWorkflowDesigner(session)


def get_team_management_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyTeamManagementWorkflow:
    return SqlAlchemyTeamManagementWorkflow(session)


def get_role_management_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyRoleManagementWorkflow:
    return SqlAlchemyRoleManagementWorkflow(session)


def get_team_workflow_designer(
    team_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyWorkflowDesigner:
    return SqlAlchemyWorkflowDesigner(session, team_id)


def get_terminal_session_gateway(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SqlAlchemyTerminalSessionGateway:
    return SqlAlchemyTerminalSessionGateway(session, settings.workspace_root)


def get_integration_discovery_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EncryptedIntegrationDiscoveryWorkflow:
    return EncryptedIntegrationDiscoveryWorkflow(session)


def get_github_installation_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EncryptedGitHubInstallationWorkflow:
    return EncryptedGitHubInstallationWorkflow(session, settings)


def get_integration_management_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EncryptedIntegrationManagementWorkflow:
    return EncryptedIntegrationManagementWorkflow(session)


def get_repository_management_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyRepositoryManagementWorkflow:
    return SqlAlchemyRepositoryManagementWorkflow(session)


def get_knowledge_search_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyKnowledgeSearchWorkflow:
    return SqlAlchemyKnowledgeSearchWorkflow(session)


def get_webhook_ingestion_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SqlAlchemyWebhookIngestionWorkflow:
    return SqlAlchemyWebhookIngestionWorkflow(session, settings)
