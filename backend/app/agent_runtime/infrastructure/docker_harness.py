"""Controller-side transport: SDKs and repository commands stay in the runner."""

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

import httpx
from pydantic import TypeAdapter

from app.agent_runtime.application.harness import TurnReceipt, WorkspaceUnavailable
from app.agent_runtime.infrastructure.container import RunnerMounts, developer_container_spec
from app.agent_runtime.infrastructure.runner import Manifest


class RunnerProtocolError(RuntimeError):
    pass


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    """Publish control data atomically; the container only has a read-only bind."""
    temporary = path.with_suffix(".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class DockerFrames:
    """Bounded Docker multiplexed logs; transport chunks need not align to frames."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.line = bytearray()

    def feed(self, data: bytes) -> list[dict[str, Any]]:
        self.buffer.extend(data)
        events = []
        while len(self.buffer) >= 8:
            stream, size = self.buffer[0], int.from_bytes(self.buffer[4:8], "big")
            if stream not in {1, 2} or self.buffer[1:4] != b"\0\0\0" or size > 131072:
                raise RunnerProtocolError("Invalid runner log frame")
            if len(self.buffer) < 8 + size:
                break
            frame = self.buffer[8 : 8 + size]
            del self.buffer[: 8 + size]
            if stream == 2:
                continue  # Raw SDK stderr is not task context or safe audit data.
            self.line.extend(frame)
            if len(self.line) > 131072:
                raise RunnerProtocolError("Runner event exceeded its bound")
            while b"\n" in self.line:
                line, _, remainder = self.line.partition(b"\n")
                self.line = bytearray(remainder)
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise RunnerProtocolError("Invalid runner event")
                events.append(event)
        return events


class DockerHarness:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        mounts: RunnerMounts,
        manifest: Manifest,
        image: str,
        network: str,
        environment: dict[str, str],
        job_id: UUID,
        lease_token: UUID,
        on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self.client, self.mounts, self.manifest = client, mounts, manifest
        self.image, self.network, self.environment = image, network, environment
        self.name = f"developer-{job_id}-{lease_token}"
        self.job_id = job_id
        self.on_progress = on_progress
        self.last_progress_at = 0.0
        self.container_id: str | None = None
        self.create_requested = False
        self.reader: asyncio.Task[None] | None = None
        self.native_id: str | None = None
        self.started: asyncio.Future[str] | None = None
        self.completed: asyncio.Future[TurnReceipt] | None = None

    async def _launch(self, native_id: str | None) -> str:
        if self.reader is not None:
            raise RunnerProtocolError("A transport instance owns exactly one native turn")
        # A named bridge is not isolation. Require an internal network and explicit proxy.
        response = await self.client.get(f"/networks/{self.network}")
        response.raise_for_status()
        if not response.json().get("Internal") or not self.environment.get("HTTPS_PROXY"):
            raise RunnerProtocolError("Runner needs an internal network and approved egress proxy")
        if self.environment.get("NO_PROXY"):
            raise RunnerProtocolError("Provider traffic must not bypass the egress proxy")
        if (self.mounts.manifest.parent / "start.json").exists():
            raise RunnerProtocolError("Controller directory has already authorized a turn")
        self.manifest = self.manifest.model_copy(update={"native_session_id": native_id})
        atomic_json(self.mounts.manifest, self.manifest.model_dump(mode="json"))
        spec = developer_container_spec(
            self.mounts,
            image=self.image,
            network=self.network,
            provider_environment=self.environment,
            read_only=self.manifest.role_kind != "DEVELOPER"
            or self.manifest.operation == "continuity",
        )
        spec["Labels"].update({"job_id": str(self.job_id), "execution_name": self.name})
        loop = asyncio.get_running_loop()
        self.started, self.completed = loop.create_future(), loop.create_future()
        self.create_requested = True
        response = await self.client.post(
            "/containers/create", params={"name": self.name}, json=spec
        )
        response.raise_for_status()
        self.container_id = response.json()["Id"]
        response = await self.client.post(f"/containers/{self.container_id}/start")
        response.raise_for_status()
        self.reader = asyncio.create_task(self._read())
        self.native_id = await asyncio.wait_for(asyncio.shield(self.started), 60)
        if native_id is not None and self.native_id != native_id:
            raise RunnerProtocolError("Runner silently replaced the native session")
        return self.native_id

    async def _read(self) -> None:
        assert self.started is not None and self.completed is not None
        try:
            frames = DockerFrames()
            async with self.client.stream(
                "GET",
                f"/containers/{self.container_id}/logs",
                params={"stdout": "true", "stderr": "true", "follow": "true"},
                timeout=None,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    for event in frames.feed(chunk):
                        if event.get("event") == "session_started":
                            value = event.get("native_session_id")
                            if (
                                self.started.done()
                                or not isinstance(value, str)
                                or not 1 <= len(value) <= 255
                            ):
                                raise RunnerProtocolError("Invalid native session event")
                            self.started.set_result(value)
                        elif event.get("event") == "developer_progress":
                            snapshot = event.get("snapshot")
                            if not isinstance(snapshot, dict) or len(json.dumps(snapshot)) > 8000:
                                raise RunnerProtocolError("Invalid progress snapshot")
                            if self.on_progress and monotonic() - self.last_progress_at >= 5:
                                await self.on_progress(snapshot)
                                self.last_progress_at = monotonic()
                        elif event.get("event") == "turn_completed":
                            if not self.started.done() or self.completed.done():
                                raise RunnerProtocolError("Receipt received out of order")
                            receipt = TypeAdapter(TurnReceipt).validate_python(event["receipt"])
                            if (
                                receipt.native_session_id != self.started.result()
                                or receipt.status not in {"completed", "failed", "interrupted"}
                            ):
                                raise RunnerProtocolError("Invalid native receipt")
                            self.completed.set_result(receipt)
                        elif event.get("event") == "runner_failed":
                            if event.get("failure_code") == "WorkspaceUnavailable":
                                raise WorkspaceUnavailable(
                                    "Check task checkout ownership and Git metadata for runner UID 10001"
                                )
                            raise RunnerProtocolError(
                                "Native runner failed; reconcile partial usage"
                            )
                        else:
                            raise RunnerProtocolError("Unknown runner protocol event")
            if not self.completed.done():
                raise RunnerProtocolError("Runner exited without a receipt")
        except BaseException as exc:  # noqa: BLE001 - deliver sanitized protocol failures to both waiters
            for future in (self.started, self.completed):
                if not future.done():
                    future.set_exception(exc)

    async def start(self) -> str:
        return await self._launch(None)

    async def resume(self, native_session_id: str) -> None:
        await self._launch(native_session_id)

    async def run_turn(self, prompt: str) -> TurnReceipt:
        if not self.native_id or self.completed is None or prompt != self.manifest.prompt:
            raise RunnerProtocolError("Turn prompt does not match its bounded manifest")
        atomic_json(
            self.mounts.manifest.parent / "start.json", {"native_session_id": self.native_id}
        )
        return await asyncio.wait_for(asyncio.shield(self.completed), self.manifest.timeout_seconds)

    async def compact(self) -> TurnReceipt:
        if self.manifest.operation != "compaction":
            raise RunnerProtocolError("Compaction requires a separately authorized manifest")
        return await self.run_turn(self.manifest.prompt)

    async def inspect(self) -> dict[str, Any]:
        return {"container_id": self.container_id, "native_session_id": self.native_id}

    async def interrupt(self) -> None:
        if self.container_id:
            response = await self.client.post(
                f"/containers/{self.container_id}/stop", params={"t": 5}
            )
            if response.status_code not in {204, 304, 404}:
                response.raise_for_status()

    async def close(self) -> None:
        try:
            if self.container_id is None and self.create_requested:
                # A lost create response may still have created a container. The deterministic
                # lease name and ownership labels let us clean up only this exact execution.
                response = await self.client.get(f"/containers/{self.name}/json")
                if response.status_code != 404:
                    response.raise_for_status()
                    metadata = response.json()
                    labels = metadata.get("Config", {}).get("Labels", {})
                    if (
                        labels.get("managed_by") != "scheduler-v2"
                        or labels.get("job_id") != str(self.job_id)
                        or labels.get("task_id") != str(self.mounts.task_id)
                        or labels.get("execution_name") != self.name
                    ):
                        raise RunnerProtocolError("Container ownership could not be verified")
                    self.container_id = metadata["Id"]
            await self.interrupt()
            if self.container_id:
                response = await self.client.delete(f"/containers/{self.container_id}")
                if response.status_code not in {204, 404}:
                    response.raise_for_status()
        finally:
            if self.reader:
                self.reader.cancel()
                await asyncio.gather(self.reader, return_exceptions=True)
            for future in (self.started, self.completed):
                if future and future.done() and not future.cancelled():
                    future.exception()  # Retrieve an unused failure from pre-turn cancellation.
