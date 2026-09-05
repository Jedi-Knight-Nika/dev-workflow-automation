from app.application.ports.github_installation import (
    GitHubInstallationAccount,
    GitHubInstallationResult,
    GitHubInstallationWorkflow,
)


class ManageGitHubInstallation:
    def __init__(self, workflow: GitHubInstallationWorkflow) -> None:
        self._workflow = workflow

    async def install_url(self) -> str:
        return await self._workflow.install_url()

    async def manage_url(self) -> str:
        return await self._workflow.manage_url()

    async def account(self) -> GitHubInstallationAccount:
        return await self._workflow.account()

    async def complete(self, installation_id: str, state: str) -> GitHubInstallationResult:
        return await self._workflow.complete(installation_id, state)
