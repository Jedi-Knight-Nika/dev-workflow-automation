import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class ManagedIntegrationNotConfigured(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ConfigureIntegrationCommand:
    provider_name: str
    provider_type: str
    status: str
    configuration: dict[str, Any]
    credential: str | None


@dataclass(frozen=True, slots=True)
class IntegrationView:
    id: uuid.UUID
    provider_type: str
    provider_name: str
    status: str
    configuration: dict[str, Any]
    has_credentials: bool
    last_error: str | None
    sync_status: str
    last_synced_at: datetime | None
    updated_at: datetime


class IntegrationManagementWorkflow(Protocol):
    async def list(self) -> list[IntegrationView]: ...
    async def configure(self, command: ConfigureIntegrationCommand) -> IntegrationView: ...
    async def verify(self, provider_name: str) -> IntegrationView: ...
