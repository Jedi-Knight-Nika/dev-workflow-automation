from typing import Any

from app.application.ports.account_settings import AccountSettingsStore


class ManageAccountSettings:
    def __init__(self, store: AccountSettingsStore) -> None:
        self._store = store

    async def get(self) -> dict[str, Any]:
        return await self._store.get()

    async def update(self, section: str, values: dict[str, Any]) -> dict[str, Any]:
        return await self._store.update(section, values)
