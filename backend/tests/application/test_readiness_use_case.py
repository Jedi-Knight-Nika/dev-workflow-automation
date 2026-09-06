import pytest

from app.application.check_readiness import CheckReadiness, ServiceUnavailableError


class FakeProbe:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = 0

    async def check(self) -> None:
        self.calls += 1
        if self.failure:
            raise self.failure


@pytest.mark.asyncio
async def test_readiness_delegates_to_probe() -> None:
    probe = FakeProbe()

    await CheckReadiness(probe).execute()

    assert probe.calls == 1


@pytest.mark.asyncio
async def test_readiness_hides_infrastructure_failure() -> None:
    probe = FakeProbe(ConnectionError("secret database details"))

    with pytest.raises(ServiceUnavailableError, match="Database unavailable"):
        await CheckReadiness(probe).execute()
