from dataclasses import dataclass
from typing import Protocol


class ProviderNotConfigured(Exception):
    pass


class ProviderNotSupported(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ProviderModelView:
    id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class ProviderCatalogView:
    provider: str
    capabilities: dict[str, bool]
    models: list[ProviderModelView]


class ProviderCatalogWorkflow(Protocol):
    async def discover(self, provider_name: str) -> ProviderCatalogView: ...
