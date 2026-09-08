from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent_runtime.infrastructure.container import RunnerMounts, developer_container_spec
from app.agent_runtime.infrastructure.container_job import run_container_job
from app.agent_runtime.infrastructure.docker_harness import atomic_json
from app.config import Settings
from app.db.models import Integration
from app.delivery.infrastructure.git_runner import GitManifest
from app.infrastructure.security.crypto import cipher
from app.integrations.github_auth import resolve_github_auth


async def github_token(session: AsyncSession) -> str:
    integration = await session.scalar(
        select(Integration).where(Integration.provider_name == "github")
    )
    if integration is None or not integration.encrypted_credentials:
        raise ValueError("Connect GitHub before V2 enrollment/publication")
    return (await resolve_github_auth(cipher.decrypt(integration.encrypted_credentials))).token


async def run_git(
    client: httpx.AsyncClient,
    settings: Settings,
    mounts: RunnerMounts,
    manifest: GitManifest,
    token: str,
    name: str,
) -> dict[str, Any]:
    network = await client.get(f"/networks/{settings.developer_container_network}")
    network.raise_for_status()
    if not network.json().get("Internal") or not settings.developer_egress_proxy:
        raise ValueError("Git transfer requires an internal network and allowlisted egress proxy")
    atomic_json(mounts.manifest, manifest.model_dump(mode="json"))
    spec = developer_container_spec(
        mounts,
        image=settings.developer_container_image,
        network=settings.developer_container_network,
        provider_environment={},
    )
    spec["Cmd"] = ["/app/.venv/bin/python", "-m", "app.delivery.infrastructure.git_runner"]
    spec["Env"] = [
        f"GITHUB_TOKEN={token}",
        f"HTTPS_PROXY={settings.developer_egress_proxy}",
        f"HTTP_PROXY={settings.developer_egress_proxy}",
    ]
    # No native session state is exposed to the credentialed publisher.
    spec["HostConfig"]["Binds"] = [
        value for value in spec["HostConfig"]["Binds"] if ":/home/runner:" not in value
    ]
    if manifest.operation == "publish":
        spec["HostConfig"]["Binds"][0] = f"{mounts.workspace}:/workspace:ro"
    return await run_container_job(client, name, spec, 360)
