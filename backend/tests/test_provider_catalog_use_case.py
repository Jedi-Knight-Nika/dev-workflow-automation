import pytest

from app.application.discover_provider_catalog import DiscoverProviderCatalog
from app.application.ports.provider_catalog import ProviderCatalogView, ProviderModelView


class FakeProviderCatalogWorkflow:
    def __init__(self) -> None:
        self.provider_name: str | None = None

    async def discover(self, provider_name: str) -> ProviderCatalogView:
        self.provider_name = provider_name
        return ProviderCatalogView(provider_name, {"chat": True}, [ProviderModelView("m1", "M1")])


@pytest.mark.asyncio
async def test_provider_catalog_delegates_discovery_through_port() -> None:
    workflow = FakeProviderCatalogWorkflow()
    catalog = await DiscoverProviderCatalog(workflow).execute("openai")
    assert workflow.provider_name == "openai"
    assert catalog.models == [ProviderModelView("m1", "M1")]
