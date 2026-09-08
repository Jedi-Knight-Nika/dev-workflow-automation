"""Bounded non-AI container operation with lease-owned cleanup."""

import asyncio
from typing import Any

import httpx

from app.agent_runtime.infrastructure.docker_harness import DockerFrames


async def _failure_detail(client: httpx.AsyncClient, container_id: str) -> str:
    """Read only a bounded diagnostic before removing a failed short-lived runner."""
    try:
        response = await client.get(
            f"/containers/{container_id}/logs",
            params={"stdout": "true", "stderr": "true"},
        )
        response.raise_for_status()
        raw = response.content
        chunks: list[bytes] = []
        offset = 0
        while offset + 8 <= len(raw) and sum(map(len, chunks)) < 8192:
            size = int.from_bytes(raw[offset + 4 : offset + 8], "big")
            if size < 0 or offset + 8 + size > len(raw):
                break
            chunks.append(raw[offset + 8 : offset + 8 + size])
            offset += 8 + size
        detail = " ".join(b"".join(chunks).decode("utf-8", "replace").split())
        return detail[-1000:]
    except Exception:  # noqa: BLE001 -- diagnostics must never mask cleanup
        return "no diagnostic output"


async def run_container_job(
    client: httpx.AsyncClient, name: str, spec: dict[str, Any], timeout: int
) -> dict[str, Any]:
    spec["Labels"]["execution_name"] = name
    container_id: str | None = None
    try:
        response = await client.post("/containers/create", params={"name": name}, json=spec)
        response.raise_for_status()
        container_id = response.json()["Id"]
        response = await client.post(f"/containers/{container_id}/start")
        response.raise_for_status()
        async with asyncio.timeout(timeout):
            response = await client.post(f"/containers/{container_id}/wait", timeout=None)
        response.raise_for_status()
        if response.json()["StatusCode"] != 0:
            detail = await _failure_detail(client, container_id)
            raise RuntimeError(f"Isolated operation failed; workspace retained for inspection: {detail}")
        frames, events = DockerFrames(), []
        async with client.stream(
            "GET", f"/containers/{container_id}/logs", params={"stdout": "true"}
        ) as logs:
            logs.raise_for_status()
            async for chunk in logs.aiter_bytes():
                events.extend(frames.feed(chunk))
                if len(events) > 1:
                    raise ValueError("Unexpected operation output")
        if len(events) != 1:
            raise ValueError("Missing operation receipt")
        return events[0]
    finally:
        if container_id is None:
            response = await client.get(f"/containers/{name}/json")
            if response.status_code != 404:
                response.raise_for_status()
                metadata = response.json()
                if metadata.get("Config", {}).get("Labels") != spec["Labels"]:
                    raise ValueError("Refusing cleanup of an unowned container")
                container_id = metadata["Id"]
        if container_id:
            response = await client.post(f"/containers/{container_id}/stop", params={"t": 5})
            if response.status_code not in {204, 304, 404}:
                response.raise_for_status()
            response = await client.delete(f"/containers/{container_id}")
            if response.status_code not in {204, 404}:
                response.raise_for_status()
