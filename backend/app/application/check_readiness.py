from app.application.ports.readiness import ReadinessProbe


class ServiceUnavailableError(RuntimeError):
    pass


class CheckReadiness:
    def __init__(self, probe: ReadinessProbe) -> None:
        self._probe = probe

    async def execute(self) -> None:
        try:
            await self._probe.check()
        except Exception as exc:
            raise ServiceUnavailableError("Database unavailable") from exc
