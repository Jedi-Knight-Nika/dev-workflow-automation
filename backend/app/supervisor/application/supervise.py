"""One admitted decision, with durable completion or failure and no implicit retries."""

from typing import Protocol, TypeVar

Decision = TypeVar("Decision")


class SupervisorPort(Protocol[Decision]):
    async def admit(self) -> Decision | None:
        """Return a saved decision, or durably reserve this attempt before returning None."""
        ...

    async def decide(self) -> Decision: ...

    async def complete(self, decision: Decision) -> None: ...

    async def fail(self, error: BaseException) -> None: ...


async def run_supervisor[Result](port: SupervisorPort[Result]) -> Result:
    cached = await port.admit()
    if cached is not None:
        return cached
    try:
        decision = await port.decide()
        await port.complete(decision)
        return decision
    except BaseException as error:
        # Cancellation must also leave a durable failed receipt, never a paid retry.
        await port.fail(error)
        raise
