from dataclasses import dataclass
from typing import Protocol


class GitHubInstallationStateInvalid(Exception):
    pass


class GitHubInstallationNotConfigured(Exception):
    pass


class GitHubAppSlugInvalid(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GitHubInstallationResult:
    redirect_url: str
    connected: bool


class GitHubInstallationWorkflow(Protocol):
    async def install_url(self) -> str: ...
    async def complete(self, installation_id: str, state: str) -> GitHubInstallationResult: ...
