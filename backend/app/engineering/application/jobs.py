"""One leased execution unit per phase, not one job per model API call."""

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.engineering.domain.lifecycle import Action, WaitReason


@dataclass(frozen=True)
class PhaseLease:
    job_id: UUID
    task_id: UUID
    token: UUID
    action: str
    lifecycle_version: int


class PhaseBlocked(RuntimeError):
    def __init__(self, reason: WaitReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class PhaseJobs(Protocol):
    async def claim(self) -> PhaseLease | None: ...
    async def heartbeat(self, lease: PhaseLease) -> bool: ...
    async def complete(self, lease: PhaseLease, action: Action) -> None: ...
    async def block(self, lease: PhaseLease, reason: WaitReason, message: str) -> None: ...
    async def recover(self) -> None: ...


class PhaseExecutor(Protocol):
    async def execute(self, lease: PhaseLease) -> Action: ...


class RunEngineeringJob:
    def __init__(
        self,
        jobs: PhaseJobs,
        executor: PhaseExecutor,
        *,
        heartbeat_seconds: float = 5,
    ) -> None:
        if heartbeat_seconds <= 0:
            raise ValueError("Heartbeat interval must be positive")
        self.jobs, self.executor = jobs, executor
        self.heartbeat_seconds = heartbeat_seconds

    async def _watch(self, lease: PhaseLease) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            if not await self.jobs.heartbeat(lease):
                return

    async def execute(self, lease: PhaseLease) -> None:
        # Revalidate immediately: queue time or a concurrent shutdown may revoke it.
        if not await self.jobs.heartbeat(lease):
            return
        operation = asyncio.create_task(self.executor.execute(lease))
        watcher = asyncio.create_task(self._watch(lease))
        try:
            done, _ = await asyncio.wait({operation, watcher}, return_when=asyncio.FIRST_COMPLETED)
            if watcher in done:
                # Includes a database outage: never keep spending with an unverifiable lease.
                watcher.result()
                raise PhaseBlocked(WaitReason.MISSING_CONFIGURATION, "Execution lease was revoked")
            action = operation.result()
            await self.jobs.complete(lease, action)
        except asyncio.CancelledError:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            await self.jobs.block(
                lease,
                WaitReason.MISSING_CONFIGURATION,
                "Controller stopped; inspect preserved session before resuming",
            )
            raise
        except PhaseBlocked as exc:
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            await self.jobs.block(lease, exc.reason, str(exc))
        except Exception as exc:  # noqa: BLE001 - sanitize the job boundary; never restart an unknown turn
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
            # Keep the durable record sanitized, but leave a bounded diagnostic in
            # controller logs so isolated runner failures are actionable.
            import structlog

            detail = " ".join(str(exc).split())[:500]
            for secret in ("GITHUB_TOKEN=", "Authorization:", "Bearer "):
                if secret in detail:
                    detail = detail.split(secret, 1)[0] + secret + "<redacted>"
            structlog.get_logger().warning(
                "phase_execution_failed", action=lease.action, error_type=type(exc).__name__, detail=detail
            )
            # SDK/transport errors can contain credentials or prompt text. Do not persist them.
            await self.jobs.block(
                lease, WaitReason.MISSING_CONFIGURATION, f"Execution failed: {type(exc).__name__}"
            )
        finally:
            operation.cancel()
            watcher.cancel()
            await asyncio.gather(operation, watcher, return_exceptions=True)
