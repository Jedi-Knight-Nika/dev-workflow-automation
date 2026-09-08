"""Pure attention and capacity policies, independent of transport and persistence."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class Scope:
    page: str = "DASHBOARD"
    task_id: str | None = None
    team_id: str | None = None


@dataclass(frozen=True)
class Evidence:
    key: str
    text: str
    source: str
    measured_at: str | None
    complete: bool = True


@dataclass(frozen=True)
class LocalExplanation:
    answer: str
    fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class Attention:
    fingerprint: str
    kind: str
    severity: str
    title: str
    facts: dict[str, Any]
    source: str
    task_id: str | None = None
    team_id: str | None = None
    hold_seconds: int = 0


@dataclass
class Snapshot:
    measured_at: str
    tasks: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    host: dict[str, Any] = field(default_factory=dict)
    services: list[dict[str, Any]] = field(default_factory=list)
    incidents: list[dict[str, Any]] = field(default_factory=list)
    partial_sources: list[str] = field(default_factory=list)
    metrics_at: str | None = None
    busy: bool | None = None
    tasks_truncated: bool = False


def number(value: Any) -> float | None:
    try:
        result = float(value) if value is not None else None
        return result if result is not None and isfinite(result) else None
    except (TypeError, ValueError):
        return None


def capacity_reason(snapshot: Snapshot, enabled: bool, reserve_mb: int) -> str | None:
    if not enabled:
        return "Local AI is disabled; deterministic facts remain available."
    if snapshot.busy is not False:
        return "Local AI is sleeping while engineering or intake work is queued or running."
    available = number(snapshot.host.get("host_memory_available"))
    if reserve_mb <= 0 or available is None or not snapshot.metrics_at:
        return "Local AI is sleeping: memory headroom has not been verified."
    try:
        age = (datetime.now(UTC) - datetime.fromisoformat(snapshot.metrics_at)).total_seconds()
    except (TypeError, ValueError):
        return "Local AI is sleeping: resource freshness is unknown."
    if age > 60 or age < -5:
        return "Local AI is sleeping: resource readings are stale."
    if available < reserve_mb * 1024 * 1024:
        return "Local AI is sleeping to preserve the configured engineering memory reserve."
    if (number(snapshot.host.get("host_cpu")) or 0) >= 85:
        return "Local AI is sleeping while host CPU is under pressure."
    if any(i.get("kind") == "OOM" and not i.get("closed_at") for i in snapshot.incidents):
        return "Local AI is sleeping after an unresolved OOM incident."
    return None


def detect(snapshot: Snapshot, thresholds: dict[str, int]) -> list[Attention]:
    result: list[Attention] = []
    for metric, kind, label, threshold in (
        ("host_cpu", "HOST_CPU_PRESSURE", "Host CPU", thresholds["cpu"]),
        ("host_memory", "HOST_MEMORY_PRESSURE", "Host memory", thresholds["memory"]),
        ("host_disk", "HOST_DISK_PRESSURE", "Host disk", thresholds["disk"]),
    ):
        value = number(snapshot.host.get(metric))
        if value is not None and value >= threshold:
            result.append(
                Attention(
                    kind,
                    kind,
                    "WARNING",
                    f"{label} is at {value:.1f}%",
                    {"measured": value, "threshold": threshold},
                    "PROMETHEUS",
                    hold_seconds=300,
                )
            )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for incident in snapshot.incidents:
        if incident.get("closed_at"):
            continue
        group = (str(incident.get("service_key", "Service")), str(incident.get("kind", "incident")))
        previous = grouped.get(group)
        if previous is None or str(incident.get("opened_at")) > str(previous.get("opened_at")):
            grouped[group] = incident
    for (service, kind), incident in grouped.items():
        key = str(incident["id"])
        running = any(
            s.get("service") == service and s.get("state") == "running" for s in snapshot.services
        )
        pressure_metric = next(
            (
                metric
                for word, metric in (
                    ("disk", "host_disk"),
                    ("memory", "host_memory"),
                    ("cpu", "host_cpu"),
                )
                if word in kind.lower()
            ),
            None,
        )
        current_pressure = number(snapshot.host.get(pressure_metric)) if pressure_metric else None
        pressure_threshold = thresholds.get(
            {"host_cpu": "cpu", "host_memory": "memory", "host_disk": "disk"}.get(
                pressure_metric or "", ""
            )
        )
        cleared_pressure = (
            current_pressure is not None
            and pressure_threshold is not None
            and current_pressure < pressure_threshold
        )
        historical = (kind == "UNAVAILABLE" and running) or cleared_pressure
        result.append(
            Attention(
                f"incident:{service}:{kind}",
                "RECORDED_INCIDENT" if historical else "SERVICE_INCIDENT",
                "INFO"
                if historical
                else "CRITICAL"
                if incident.get("severity", "").upper() == "CRITICAL"
                else "WARNING",
                f"{service}: earlier {kind.lower()} record is unclosed; current container/pressure readings have recovered"
                if historical
                else f"{service}: recorded {kind.lower()} incident is open",
                {
                    "incident_id": key,
                    "opened_at": incident.get("opened_at"),
                    "current_container_running": running,
                    "current_pressure": current_pressure,
                },
                "INCIDENTS",
            )
        )
    for task in snapshot.tasks:
        if task["status"] in {"MERGED", "CANCELLED"}:
            continue
        identity = f"{task['id']}:{task['requirement_version']}"
        label = task["label"]
        common = {"task_id": task["id"], "team_id": task["team_id"]}
        known, limit = number(task.get("known_cost_usd")), number(task.get("budget_usd"))
        if known is not None and limit and limit > 0 and known >= limit * 0.8:
            result.append(
                Attention(
                    f"budget:{identity}",
                    "TASK_BUDGET_PRESSURE",
                    "WARNING",
                    f"{label}: {known / limit:.0%} of task budget used",
                    {
                        "known_cost_usd": known,
                        "budget_usd": limit,
                        "unknown_runs": task.get("unknown_cost_runs"),
                    },
                    "AI_RUNS",
                    **common,
                )
            )
        if task.get("unknown_stopped_runs", 0):
            result.append(
                Attention(
                    f"billing:{identity}",
                    "UNKNOWN_COST_BLOCK",
                    "WARNING",
                    f"{label}: stopped AI usage has unknown cost",
                    {"runs": task["unknown_stopped_runs"]},
                    "AI_RUNS",
                    **common,
                )
            )
        for field_name, threshold, kind, text in (
            (
                "consecutive_validation_failures",
                3,
                "VALIDATION_FAILURE_REPEAT",
                "consecutive validation failures",
            ),
            ("no_progress_count", 2, "NO_PROGRESS_REPEAT", "no-progress reports"),
        ):
            if task.get(field_name, 0) >= threshold:
                result.append(
                    Attention(
                        f"{kind}:{identity}",
                        kind,
                        "WARNING",
                        f"{label}: {task[field_name]} {text}",
                        {"count": task[field_name], "threshold": threshold},
                        "TASKS",
                        **common,
                    )
                )
        if task["status"] in {"WAITING_HUMAN", "FAILED"}:
            result.append(
                Attention(
                    f"attention:{identity}",
                    "MANUAL_ATTENTION_REQUIRED",
                    "WARNING",
                    f"{label}: {task['status'].replace('_', ' ').lower()}",
                    {"stage": task["stage"], "wait_reason": task["wait_reason"]},
                    "TASKS",
                    **common,
                )
            )
    return result


def choose_tools(question: str, scope: Scope) -> list[str]:
    """No model purchase or recursive loop is needed to route common questions."""
    text = question.lower()
    if text.strip(" !?.") in {"hi", "hello", "hey", "hey jarvis", "hello jarvis", "გამარჯობა"}:
        return ["product"]
    groups = (
        (
            ("cost", "token", "expens", "budget", "cheap", "spend", "compaction", "model", "agent"),
            "ai_usage",
        ),
        (
            ("ram", "memory", "cpu", "resource", "capacity", "host", "disk", "another task"),
            "resources",
        ),
        (("incident", "outage", "downtime", "restart", "oom", "unavailable"), "incidents"),
        (("forecast", "predict", "next week", "next month", "queue drain"), "forecasts"),
        (("why", "task", "fail", "validation", "review", "progress", "queue"), "tasks"),
        (("changed", "overnight", "visit", "recent"), "changes"),
        (("you", "observer", "how", "workflow", "work flow", "can do"), "product"),
    )
    tools = [name for words, name in groups if any(word in text for word in words)]
    if scope.task_id and "tasks" not in tools:
        tools.insert(0, "tasks")
    return (tools or ["attention", "tasks", "resources"])[:4]


def question_subject(question: str, history: list[dict[str, Any]]) -> str:
    followups = {"what", "why", "", "explain", "what do you mean"}
    if question.lower().strip(" ?!.") not in followups:
        return question
    previous = [r["content"] for r in history if r.get("role") == "user"]
    if previous and previous[-1] == question:
        previous.pop()
    return next(
        (value for value in reversed(previous) if value.lower().strip(" ?!.") not in followups),
        question,
    )


def capacity_question(question: str) -> bool:
    value = question.lower()
    return any(
        term in value
        for term in (
            "another task",
            "another runner",
            "capacity",
            "safe to start",
            "can i start",
            "can the host",
        )
    )


def capacity_advice(snapshot: Snapshot) -> str:
    disk = number(snapshot.host.get("host_disk"))
    memory = number(snapshot.host.get("host_memory"))
    if disk is not None and disk >= 90:
        return f"I would not start another task now: disk usage is {disk:.1f}%. Free disk space first. Low CPU alone does not establish safe capacity. This is advice, not a scheduling action."
    if memory is not None and memory >= 85:
        return f"I would not start another task now: RAM usage is {memory:.1f}%. Preserve memory for existing work. No scheduling action was taken."
    return "I cannot confirm that another task is safe to start. That requires fresh free-memory and disk readings, the new runner's resource limits and Team concurrency policy. Low CPU alone is not enough. No scheduling action was taken."
