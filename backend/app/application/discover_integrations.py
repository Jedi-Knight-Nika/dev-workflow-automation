from app.application.ports.integration_discovery import (
    IntegrationDiscoveryWorkflow,
    RepositoryDiscoveryView,
    WorkflowStateView,
)


class DiscoverIntegrations:
    def __init__(self, workflow: IntegrationDiscoveryWorkflow) -> None:
        self._workflow = workflow

    async def github_repositories(self) -> list[RepositoryDiscoveryView]:
        return await self._workflow.github_repositories()

    async def linear_workflow_states(self) -> list[WorkflowStateView]:
        return await self._workflow.linear_workflow_states()
