import uuid

from app.application.ports.terminal_sessions import (
    OpenTerminalCommand,
    TerminalAccess,
    TerminalSessionGateway,
)


class ManageTerminal:
    def __init__(self, gateway: TerminalSessionGateway) -> None:
        self._gateway = gateway

    async def open(self, command: OpenTerminalCommand) -> TerminalAccess:
        return await self._gateway.open(command)

    async def close(self, session_id: uuid.UUID) -> bool:
        return await self._gateway.close(session_id)
