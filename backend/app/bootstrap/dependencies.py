from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.provider_catalog import EncryptedProviderCatalogWorkflow
from app.engineering.application.query_events import QueryEvents
from app.engineering.infrastructure.conversation import SqlAlchemyTaskConversationStore
from app.engineering.infrastructure.event_queries import SqlAlchemyEventQueries
from app.engineering.infrastructure.history import SqlAlchemyTaskHistoryQueries
from app.engineering.infrastructure.queries import SqlAlchemyTaskQueries
from app.engineering.infrastructure.task_controls import SqlAlchemyTaskLifecycleUnitOfWorkFactory
from app.engineering.infrastructure.unit_of_work import SqlAlchemyUnitOfWork
from app.intake.infrastructure.webhook_ingestion import SqlAlchemyWebhookIngestionWorkflow
from app.platform.configuration.settings import Settings, get_settings
from app.platform.configuration.store import SqlAlchemyAccountSettingsStore
from app.platform.integrations.infrastructure.discovery import EncryptedIntegrationDiscoveryWorkflow
from app.platform.integrations.infrastructure.github_installation import (
    EncryptedGitHubInstallationWorkflow,
)
from app.platform.integrations.infrastructure.management import (
    EncryptedIntegrationManagementWorkflow,
)
from app.platform.persistence.readiness import SqlAlchemyReadinessProbe
from app.platform.persistence.session import SessionLocal, get_session
from app.platform.scheduling.queries import SqlAlchemyOperationsQueries
from app.platform.scheduling.worker_queries import SqlAlchemyWorkerQueries
from app.platform.telemetry.dashboard import SqlAlchemyDashboardQueries
from app.platform.telemetry.host_collector import PsutilHostTelemetryCollector
from app.repositories.infrastructure.management import (
    SqlAlchemyRepositoryManagementWorkflow,
)
from app.teams.infrastructure.management import SqlAlchemyTeamManagementWorkflow


def get_unit_of_work(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def get_account_settings_store(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyAccountSettingsStore:
    return SqlAlchemyAccountSettingsStore(session)


def get_event_queries() -> QueryEvents:
    return QueryEvents(SqlAlchemyEventQueries(SessionLocal))


def get_readiness_probe(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyReadinessProbe:
    return SqlAlchemyReadinessProbe(session)


def get_task_lifecycle_factory() -> SqlAlchemyTaskLifecycleUnitOfWorkFactory:
    return SqlAlchemyTaskLifecycleUnitOfWorkFactory(SessionLocal)


def get_task_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyTaskQueries:
    return SqlAlchemyTaskQueries(session)


def get_task_history_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyTaskHistoryQueries:
    return SqlAlchemyTaskHistoryQueries(session)


def get_task_conversation_store(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyTaskConversationStore:
    return SqlAlchemyTaskConversationStore(session)


def get_operations_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyOperationsQueries:
    return SqlAlchemyOperationsQueries(session)


def get_dashboard_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyDashboardQueries:
    return SqlAlchemyDashboardQueries(session)


def get_telemetry_collector() -> PsutilHostTelemetryCollector:
    return PsutilHostTelemetryCollector()


def get_provider_catalog_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EncryptedProviderCatalogWorkflow:
    return EncryptedProviderCatalogWorkflow(session)


def get_worker_queries(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyWorkerQueries:
    return SqlAlchemyWorkerQueries(session)


def get_team_management_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SqlAlchemyTeamManagementWorkflow:
    return SqlAlchemyTeamManagementWorkflow(session)


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


def get_webhook_ingestion_workflow(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SqlAlchemyWebhookIngestionWorkflow:
    return SqlAlchemyWebhookIngestionWorkflow(session, settings)
