from app.application.ports.provider_catalog import ProviderCatalogView, ProviderCatalogWorkflow


class DiscoverProviderCatalog:
    def __init__(self, workflow: ProviderCatalogWorkflow) -> None:
        self._workflow = workflow

    async def execute(self, provider_name: str) -> ProviderCatalogView:
        return await self._workflow.discover(provider_name)
