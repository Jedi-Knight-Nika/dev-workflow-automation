"""Unpaid live acceptance; run inside the engineering-acceptance worker image.

Requires the acceptance Compose overlay and /var/run/docker.sock. Refuses other
databases/projects or an enabled scheduler. Creates one clearly labelled paused
test task, retains its observation history, and removes only its own containers.
Temporarily stops and restores the acceptance Prometheus to test failure isolation.
"""

import asyncio
import json
import time
from uuid import uuid4

import httpx
from sqlalchemy import func, select

import app.platform.persistence.registry  # noqa: F401
from app.agent_runtime.infrastructure.models import AIRun, DeveloperSession
from app.bootstrap.observability import get_metrics_adapter, supporting_sessions
from app.engineering.infrastructure.task_models import Task
from app.observability.domain.metrics import Metric, MetricQuery
from app.observability.infrastructure.docker_events import DockerEventsAdapter
from app.observability.infrastructure.models import (
    InfrastructureEvent,
    RunnerResourceBinding,
    RunnerResourceSummary,
)
from app.platform.configuration.settings import get_settings
from app.teams.infrastructure.models import TeamAgentProfile


async def main():
    settings = get_settings()
    sessions = supporting_sessions()
    url = sessions.kw["bind"].url
    assert url.database == "acceptance" and url.username == "acceptance"
    assert settings.observability_compose_project == "engineering-acceptance"
    assert not settings.scheduler_enabled
    task_id = uuid4()
    async with sessions.begin() as session:
        profile = await session.scalar(
            select(TeamAgentProfile).where(TeamAgentProfile.role_kind == "DEVELOPER")
        )
        assert profile
        profile_id, team_id = profile.id, profile.team_id
        before_receipts = await session.scalar(select(func.count()).select_from(AIRun))
        session.add(
            Task(
                id=task_id,
                title="[Acceptance] Unpaid monitoring validation",
                status="PAUSED",
                stage="VALIDATING",
                team_id=team_id,
            )
        )
        await session.flush()
        session.add(
            DeveloperSession(
                task_id=task_id,
                profile_id=profile_id,
                harness="test",
                harness_version="acceptance",
                provider="none",
                model="no-inference",
                workspace_path="/unused",
                state_path="/unused",
            )
        )
    print(json.dumps({"task_id": str(task_id), "paid_execution": False}), flush=True)
    async with httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(uds="/var/run/docker.sock"),
        base_url="http://docker",
        timeout=10,
    ) as docker:
        observer = DockerEventsAdapter(
            docker,
            sessions,
            get_metrics_adapter(),
            host=settings.observability_host_id,
            project=settings.observability_compose_project,
        )

        async def workload(seconds, suffix):
            # No environment credentials, mounts, network or inference; bounded CPU/RAM.
            script = f"import time, hashlib; b=bytearray(16*1024*1024); end=time.monotonic()+{seconds}; n=0\nwhile time.monotonic()<end: hashlib.sha256(b).digest(); n+=1; time.sleep(.02)\nprint(n)"
            response = await docker.post(
                "/containers/create",
                params={"name": f"developer-observability-{task_id}-{suffix}"},
                json={
                    "Image": "engineering-acceptance-api:local",
                    "Entrypoint": ["/app/.venv/bin/python", "-c", script],
                    "Cmd": [],
                    "User": "10001:10001",
                    "Env": [],
                    "Labels": {"managed_by": "scheduler-v2", "task_id": str(task_id)},
                    "HostConfig": {
                        "NetworkMode": "none",
                        "ReadonlyRootfs": True,
                        "CapDrop": ["ALL"],
                        "SecurityOpt": ["no-new-privileges:true"],
                        "Memory": 128 * 1024 * 1024,
                        "NanoCpus": 250000000,
                        "PidsLimit": 32,
                    },
                },
            )
            response.raise_for_status()
            identifier = response.json()["Id"]
            started = time.monotonic()
            try:
                (await docker.post(f"/containers/{identifier}/start")).raise_for_status()
                deadline = time.monotonic() + seconds + 30
                while time.monotonic() < deadline:
                    state = (await docker.get(f"/containers/{identifier}/json")).json()["State"]
                    if not state["Running"]:
                        assert state["ExitCode"] == 0, state
                        break
                    await asyncio.sleep(2)
                else:
                    raise AssertionError("Unpaid workload did not finish")
            finally:
                (
                    await docker.delete(f"/containers/{identifier}", params={"force": "true"})
                ).raise_for_status()
            await observer.collect()
            async with sessions() as session:
                binding = await session.scalar(
                    select(RunnerResourceBinding).where(
                        RunnerResourceBinding.container_id == identifier
                    )
                )
                assert binding and binding.task_id == task_id and binding.team_id == team_id
                assert (
                    binding.agent_profile_id == profile_id
                    and binding.stopped_at
                    and binding.exit_code == 0
                )
                count = await session.scalar(
                    select(func.count())
                    .select_from(InfrastructureEvent)
                    .where(InfrastructureEvent.container_id == identifier)
                )
                runner_id = binding.runner_run_id
            await observer.collect()
            async with sessions() as session:
                repeated = await session.scalar(
                    select(func.count())
                    .select_from(InfrastructureEvent)
                    .where(InfrastructureEvent.container_id == identifier)
                )
                assert repeated == count and count >= 3
            print(
                json.dumps(
                    {
                        "workload": suffix,
                        "duration_seconds": round(time.monotonic() - started, 2),
                        "events": count,
                        "attribution": "passed",
                        "deduplication": "passed",
                    }
                ),
                flush=True,
            )
            return runner_id

        runner_id = await workload(45, "collectors-on")
        deadline = time.monotonic() + 80
        while time.monotonic() < deadline:
            await observer.finalize()
            async with sessions() as session:
                summary = await session.get(RunnerResourceSummary, runner_id)
                if summary:
                    assert summary.values["max_memory_bytes"] is not None, summary.values
                    assert summary.values["cpu_seconds"] is not None, summary.values
                    print(
                        json.dumps(
                            {
                                "summary": summary.values,
                                "coverage": float(summary.sample_coverage_ratio)
                                if summary.sample_coverage_ratio is not None
                                else None,
                                "complete": summary.metrics_complete,
                            }
                        ),
                        flush=True,
                    )
                    break
            await asyncio.sleep(3)
        else:
            raise AssertionError("Resource summary was not finalized")

        async with httpx.AsyncClient(base_url="http://backend:8000", timeout=12) as api:
            token = settings.observability_alert_token
            from datetime import UTC, datetime

            started_at = datetime.now(UTC).isoformat()
            alert = {
                "status": "firing",
                "fingerprint": task_id.hex,
                "startsAt": started_at,
                "labels": {
                    "service": "acceptance-validation",
                    "alertname": "AcceptanceProbe",
                    "secret": "must-not-persist",
                },
                "annotations": {"description": "must-not-persist"},
            }
            assert (
                await api.post("/api/v1/observability/alerts", json={"alerts": [alert]})
            ).status_code == 401
            headers = {"authorization": f"Bearer {token}"}
            for status in ["firing", "firing", "resolved"]:
                alert["status"] = status
                if status == "resolved":
                    alert["endsAt"] = datetime.now(UTC).isoformat()
                (
                    await api.post(
                        "/api/v1/observability/alerts", json={"alerts": [alert]}, headers=headers
                    )
                ).raise_for_status()
            incidents = (await api.get("/api/v1/observability/incidents")).json()
            matched = [i for i in incidents if i["dedup_key"].startswith(task_id.hex)]
            assert len(matched) == 1 and matched[0]["closed_at"]
            assert "must-not-persist" not in json.dumps(matched)
            print("Alert authorization, deduplication, resolution and privacy: passed", flush=True)

            prometheus = (
                await docker.get("/containers/engineering-acceptance-prometheus-1/json")
            ).json()
            assert (
                prometheus["Config"]["Labels"]["com.docker.compose.project"]
                == "engineering-acceptance"
            )
            prom_id = prometheus["Id"]
            try:
                (
                    await docker.post(f"/containers/{prom_id}/stop", params={"t": "10"})
                ).raise_for_status()
                print("Acceptance Prometheus stopped for outage check", flush=True)
                await workload(5, "collectors-off-short")
                result = await get_metrics_adapter().instant(MetricQuery(Metric.HOST_CPU))
                assert result.status in {"unavailable", "stale"}
                for path in [
                    "/health/ready",
                    "/api/v1/observability/live",
                    "/api/v1/analytics/ai?days=30",
                    "/api/v1/tasks",
                ]:
                    (await api.get(path)).raise_for_status()
                print(
                    "Unpaid execution and API availability during monitoring outage: passed",
                    flush=True,
                )
            finally:
                (await docker.post(f"/containers/{prom_id}/start")).raise_for_status()
                print("Acceptance Prometheus restarted", flush=True)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(AIRun)) == before_receipts
    print("V2.1 live acceptance passed; no AI receipts created", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
