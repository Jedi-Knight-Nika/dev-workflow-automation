from app.platform.integrations.infrastructure.management import integration_display_status
from app.platform.integrations.models import Integration
from app.platform.scheduling.states import IntegrationStatus


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
