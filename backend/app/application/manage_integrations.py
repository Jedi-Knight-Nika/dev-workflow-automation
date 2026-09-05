from app.application.ports.integration_management import (
    ConfigureIntegrationCommand,
    IntegrationManagementWorkflow,
    IntegrationView,
)


class ManageIntegrations:
    def __init__(self, workflow: IntegrationManagementWorkflow) -> None:
        self._workflow = workflow

    async def list(self) -> list[IntegrationView]:
        return await self._workflow.list()

    async def configure(self, command: ConfigureIntegrationCommand) -> IntegrationView:
        return await self._workflow.configure(command)

    async def verify(self, provider_name: str) -> IntegrationView:
        return await self._workflow.verify(provider_name)
