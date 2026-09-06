from app.db.models import IndexStatus, Integration, IntegrationStatus, Repository
from app.infrastructure.integration_management import integration_display_status
from app.infrastructure.persistence.repository_management import (
    SqlAlchemyRepositoryManagementWorkflow,
)


def test_integration_display_status_uses_shared_resource_vocabulary() -> None:
    integration = Integration(
        provider_name="trello",
        provider_type="task_management",
        status=IntegrationStatus.CONNECTED,
        sync_status="RUNNING",
    )
    assert integration_display_status(integration) == "WORKING"
    integration.sync_status = "READY"
    assert integration_display_status(integration) == "READY"
    integration.status = IntegrationStatus.ERROR
    assert integration_display_status(integration) == "NEEDS_ATTENTION"


def test_repository_status_separates_code_and_knowledge_health() -> None:
    repository = Repository(
        provider="github",
        external_repo_id="1",
        owner="owner",
        name="repo",
        clone_url="https://example.test/repo.git",
        default_branch="main",
        enabled=True,
        local_path="/cache/repo",
        latest_sha="new",
        indexed_sha="old",
        index_status=IndexStatus.READY,
    )

    assert SqlAlchemyRepositoryManagementWorkflow._code_status(repository) == "READY"
    assert SqlAlchemyRepositoryManagementWorkflow._knowledge_status(repository) == "OUT_OF_DATE"
