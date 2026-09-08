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


@dataclass(frozen=True, slots=True)
class GitHubInstallationAccount:
    login: str
    account_type: str
    avatar_url: str
    profile_url: str


class GitHubInstallationWorkflow(Protocol):
    async def install_url(self) -> str: ...
    async def manage_url(self) -> str: ...
    async def account(self) -> GitHubInstallationAccount: ...
    async def complete(self, installation_id: str, state: str) -> GitHubInstallationResult: ...
