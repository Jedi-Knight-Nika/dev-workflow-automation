"""Read-only Docker observation inside the existing trusted controller only.

No execution path waits for this collector. Replayed events are idempotent; a
collector outage can lose Docker's bounded event backlog, never a coding lease.
"""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent_runtime.infrastructure.models import DeveloperSession
from app.engineering.infrastructure.task_models import Task
from app.observability.application.ports import MetricsQueryPort
from app.observability.domain.metrics import Metric, MetricQuery, MetricRangeQuery
from app.observability.domain.resources import summarize
from app.observability.infrastructure.models import (
    InfrastructureEvent,
    RunnerResourceBinding,
    RunnerResourceSummary,
    ServiceIncident,
)

log = structlog.get_logger()
from app.observability.infrastructure.configuration import preferences
from app.observability.infrastructure.models import ContainerObservation

EVENTS = {
    "create",
    "start",
    "restart",
    "die",
    "oom",
    "kill",
    "destroy",
    "health_status: healthy",
    "health_status: unhealthy",
}


def event_identity(event: dict[str, Any], host: str, project: str) -> dict[str, Any] | None:
    actor = event.get("Actor", {})
    labels = actor.get("Attributes", {})
    managed = labels.get("managed_by") == "scheduler-v2"
    if not managed and labels.get("com.docker.compose.project") != project:
        return None
    container_id = actor.get("ID", "")
    action = event.get("Action", "")
    if not re.fullmatch(r"[a-f0-9]{64}", container_id) or action not in EVENTS:
        return None
    stamp = event.get("timeNano") or event.get("time", 0) * 1000000000
    if not isinstance(stamp, int) or stamp <= 0:
        return None
    name = labels.get("name", "")[:255]
    kind = (
        "DEVELOPER"
        if name.startswith("developer-")
        else "VALIDATOR"
        if name.startswith("validation-")
        else "GIT_TRANSFER"
        if name.startswith(("prepare-", "publish-"))
        else "OTHER"
    )
    service = labels.get("com.docker.compose.service", kind.lower())
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", service):
        service = "other"
    try:
        task_id = UUID(labels["task_id"]) if managed else None
    except (ValueError, KeyError):
        task_id = None
    exit_code = labels.get("exitCode")
    return {
        "id": uuid5(NAMESPACE_URL, f"{host}:{container_id}:{action}:{stamp}"),
        "occurred_at": datetime.fromtimestamp(stamp / 1e9, UTC),
        "host_id": host,
        "container_id": container_id,
        "service_name": service,
        "runner_run_id": uuid5(NAMESPACE_URL, f"{host}:{container_id}") if managed else None,
        "event_type": action,
        "exit_code": int(exit_code)
        if isinstance(exit_code, str) and re.fullmatch(r"-?[0-9]{1,4}", exit_code)
        else None,
        "oom_killed": True if action == "oom" else None,
        "task_id": task_id,
        "kind": kind,
        "name": name,
    }


class DockerEventsAdapter:
    def __init__(
        self,
        client: httpx.AsyncClient,
        sessions: async_sessionmaker[AsyncSession],
        metrics: MetricsQueryPort,
        *,
        host: str,
        project: str,
    ) -> None:
        self.client, self.sessions, self.metrics, self.host, self.project = (
            client,
            sessions,
            metrics,
            host,
            project,
        )

    async def record(self, raw: dict[str, Any]) -> None:
        value = event_identity(raw, self.host, self.project)
        if value is None:
            return
        task_id, kind, name = value.pop("task_id"), value.pop("kind"), value.pop("name")
        async with self.sessions.begin() as session:
            await session.execute(
                insert(InfrastructureEvent).values(**value).on_conflict_do_nothing()
            )
            runner_id = value["runner_run_id"]
            if runner_id:
                binding = await session.scalar(
                    select(RunnerResourceBinding).where(
                        RunnerResourceBinding.runner_run_id == runner_id
                    )
                )
                if binding is None and value["event_type"] == "start":
                    task = await session.get(Task, task_id) if task_id else None
                    native = (
                        await session.scalar(
                            select(DeveloperSession)
                            .where(DeveloperSession.task_id == task_id)
                            .order_by(DeveloperSession.generation.desc())
                            .limit(1)
                        )
                        if task
                        else None
                    )
                    await session.execute(
                        insert(RunnerResourceBinding)
                        .values(
                            id=runner_id,
                            runner_run_id=runner_id,
                            container_id=value["container_id"],
                            container_name=name,
                            service_kind=kind,
                            task_id=task.id if task else None,
                            team_id=task.team_id if task else None,
                            agent_profile_id=native.profile_id
                            if native and kind == "DEVELOPER"
                            else None,
                            role="DEVELOPER" if kind == "DEVELOPER" else None,
                            phase=task.stage if task else None,
                            host_id=self.host,
                            started_at=value["occurred_at"],
                        )
                        .on_conflict_do_nothing()
                    )
                elif binding:
                    if value["event_type"] in {"die", "destroy"}:
                        binding.stopped_at = binding.stopped_at or value["occurred_at"]
                        if value["exit_code"] is not None:
                            binding.exit_code = value["exit_code"]
                    if value["oom_killed"]:
                        binding.oom_killed = True
            if value["event_type"] in {"oom", "health_status: unhealthy"} or (
                value["event_type"] == "die" and value["exit_code"] not in (None, 0)
            ):
                await session.execute(
                    insert(ServiceIncident)
                    .values(
                        dedup_key=str(value["id"]),
                        service_key=value["service_name"],
                        kind="OOM" if value["oom_killed"] else "UNAVAILABLE",
                        severity="critical",
                        opened_at=value["occurred_at"],
                        source="docker",
                        summary=f"{value['service_name']}: {value['event_type']}",
                    )
                    .on_conflict_do_nothing()
                )
            if value["event_type"] == "health_status: healthy":
                from sqlalchemy import update

                await session.execute(
                    update(ServiceIncident)
                    .where(
                        ServiceIncident.source == "docker",
                        ServiceIncident.service_key == value["service_name"],
                        ServiceIncident.kind == "UNAVAILABLE",
                        ServiceIncident.closed_at.is_(None),
                    )
                    .values(closed_at=value["occurred_at"])
                )

    async def collect(self) -> None:
        async with self.sessions() as session:
            last = await session.scalar(
                select(InfrastructureEvent.occurred_at)
                .where(InfrastructureEvent.host_id == self.host)
                .order_by(InfrastructureEvent.occurred_at.desc())
                .limit(1)
            )
        since = last or datetime.now(UTC) - timedelta(minutes=10)
        # Finite event windows avoid an unbounded stream and leave retries independent
        # of execution. Overlap recovers out-of-order delivery; UUIDs deduplicate.
        params = {
            "since": str(int(since.timestamp()) - 2),
            "until": str(int(datetime.now(UTC).timestamp())),
            "filters": json.dumps({"type": ["container"]}),
        }
        async with self.client.stream("GET", "/events", params=params) as response:
            response.raise_for_status()
            count = 0
            async for line in response.aiter_lines():
                count += 1
                if len(line) > 65536 or count > 4096:
                    raise ValueError("Docker event batch exceeded bound")
                if line:
                    await self.record(json.loads(line))

    async def reconcile(self) -> None:
        response = await self.client.get("/containers/json", params={"all": "true"})
        response.raise_for_status()
        owned = [
            c
            for c in response.json()
            if c.get("Labels", {}).get("managed_by") == "scheduler-v2"
            or c.get("Labels", {}).get("com.docker.compose.project") == self.project
        ]
        for container in owned[:200]:
            identifier = container["Id"]
            inspected = await self.client.get(f"/containers/{identifier}/json")
            if inspected.status_code == 404:
                continue
            inspected.raise_for_status()
            value = inspected.json()
            state, labels = value["State"], value["Config"].get("Labels") or {}
            started = state.get("StartedAt", "")
            instant = (
                datetime.fromisoformat(started)
                if started and not started.startswith("0001")
                else None
            )
            attributes = {**labels, "name": value["Name"].lstrip("/")}
            if instant and labels.get("managed_by") == "scheduler-v2":
                async with self.sessions() as session:
                    exists = await session.scalar(
                        select(RunnerResourceBinding.id).where(
                            RunnerResourceBinding.container_id == identifier
                        )
                    )
                if not exists:
                    await self.record(
                        {
                            "Action": "start",
                            "timeNano": int(instant.timestamp() * 1e9),
                            "Actor": {"ID": identifier, "Attributes": attributes},
                        }
                    )
            observed = {
                "name": attributes["name"],
                "service": labels.get("com.docker.compose.service"),
                "state": state["Status"],
                "health": state.get("Health", {}).get("Status", "unknown"),
                "restart_count": value.get("RestartCount"),
                "oom_killed": state.get("OOMKilled"),
                "exit_code": state.get("ExitCode") if not state.get("Running") else None,
                "uptime_seconds": max(0, (datetime.now(UTC) - instant).total_seconds())
                if instant and state.get("Running")
                else None,
            }
            async with self.sessions.begin() as session:
                statement = insert(ContainerObservation).values(
                    container_id=identifier,
                    host_id=self.host,
                    sampled_at=datetime.now(UTC),
                    values=observed,
                )
                await session.execute(
                    statement.on_conflict_do_update(
                        index_elements=[ContainerObservation.container_id],
                        set_={"sampled_at": statement.excluded.sampled_at, "values": observed},
                    )
                )
            if (
                not state.get("Running")
                and state.get("FinishedAt")
                and not state["FinishedAt"].startswith("0001")
            ):
                finished = datetime.fromisoformat(state["FinishedAt"])
                await self.record(
                    {
                        "Action": "die",
                        "timeNano": int(finished.timestamp() * 1e9),
                        "Actor": {
                            "ID": identifier,
                            "Attributes": {**attributes, "exitCode": str(state.get("ExitCode", 0))},
                        },
                    }
                )

    async def finalize(self) -> None:
        async with self.sessions() as session:
            bindings = list(
                await session.scalars(
                    select(RunnerResourceBinding)
                    .outerjoin(
                        RunnerResourceSummary,
                        RunnerResourceSummary.runner_run_id == RunnerResourceBinding.runner_run_id,
                    )
                    .where(
                        RunnerResourceBinding.stopped_at
                        < datetime.now(UTC) - timedelta(seconds=30),
                        RunnerResourceSummary.runner_run_id.is_(None),
                    )
                    .order_by(RunnerResourceBinding.stopped_at)
                    .limit(4)
                )
            )
        for binding in bindings:
            if binding.stopped_at is None:
                continue
            end = binding.stopped_at
            duration = (end - binding.started_at).total_seconds()
            if duration <= 0 or duration > 31 * 86400:
                continue
            samples = {}
            for metric in (
                Metric.LAST_SEEN,
                Metric.CPU_SECONDS,
                Metric.THROTTLED_SECONDS,
                Metric.MEMORY,
                Metric.NETWORK_RX,
                Metric.NETWORK_TX,
                Metric.BLOCK_READ,
                Metric.BLOCK_WRITE,
                Metric.PIDS,
            ):
                result = await self.metrics.range(
                    MetricRangeQuery(
                        MetricQuery(metric, container_id=binding.container_id),
                        binding.started_at,
                        end,
                        max(10, int(duration / 2999) + 1),
                    )
                )
                samples[metric.value] = (
                    result.series[0].samples
                    if len(result.series) == 1 and result.status == "available"
                    else []
                )
            summary = summarize(samples, binding.started_at.timestamp(), end.timestamp())
            async with self.sessions.begin() as session:
                observation = await session.get(ContainerObservation, binding.container_id)
                await session.execute(
                    insert(RunnerResourceSummary)
                    .values(
                        runner_run_id=binding.runner_run_id,
                        sample_start_at=binding.started_at,
                        sample_end_at=end,
                        sample_coverage_ratio=summary.sample_coverage_ratio,
                        metrics_complete=summary.metrics_complete,
                        values={
                            **summary.values,
                            "oom_count": 1
                            if binding.oom_killed
                            else 0
                            if observation and observation.values.get("oom_killed") is False
                            else None,
                            "restart_count": observation.values.get("restart_count")
                            if observation
                            else None,
                        },
                    )
                    .on_conflict_do_nothing()
                )

    async def run(self) -> None:
        while True:
            try:
                async with asyncio.timeout(20):
                    if (await preferences(self.sessions)).get("enabled", True):
                        await self.collect()
                        await self.reconcile()
                        await self.finalize()
            except Exception as exc:  # noqa: BLE001 - telemetry must never break execution
                log.warning("observability_collection_unavailable", failure_code=type(exc).__name__)
            await asyncio.sleep(5)
