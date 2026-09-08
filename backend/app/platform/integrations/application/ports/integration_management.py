import uuid
from dataclasses import dataclass, field
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
    display_status: str = "NOT_CONFIGURED"
    usage: dict[str, int] = field(default_factory=dict)


class IntegrationManagementWorkflow(Protocol):
    async def list(self) -> list[IntegrationView]: ...
    async def configure(self, command: ConfigureIntegrationCommand) -> IntegrationView: ...
    async def verify(self, provider_name: str) -> IntegrationView: ...
    async def request_sync(self, provider_name: str) -> IntegrationView: ...
