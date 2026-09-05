"""Observe and validate one credential-backed MVP workflow against a running stack."""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

TERMINAL_FAILURES = {"FAILED", "CANCELLED", "NEEDS_HUMAN", "CONTEXT_PENDING"}
REQUIRED_ROLES = {"INTAKE", "THINKER", "EXECUTOR", "REVIEWER"}
SUCCESSFUL_CHECKS = {"SUCCESS", "NEUTRAL", "SKIPPED"}
BLOCKING_VALIDATIONS = {"FAILURE", "FAILED", "ERROR", "CHANGES_REQUESTED", "ACTION_REQUIRED"}


def request(base_url: str, path: str, method: str = "GET") -> Any:
    target = f"{base_url.rstrip('/')}/api/v1{path}"
    call = urllib.request.Request(target, method=method)
    try:
        with urllib.request.urlopen(call, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {target} failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach {target}: {exc.reason}") from exc


def find_task(base_url: str, external_key: str) -> dict[str, Any] | None:
    tasks = request(base_url, "/tasks?limit=500")
    return next((task for task in tasks if task.get("external_key") == external_key), None)


def validate_history(
    task: dict[str, Any],
    jobs: list[dict[str, Any]],
    events: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    require_repair: bool,
) -> list[str]:
    succeeded_roles = {str(job["role"]) for job in jobs if job.get("state") == "SUCCEEDED"}
    problems = (
        [f"missing successful roles: {', '.join(sorted(REQUIRED_ROLES - succeeded_roles))}"]
        if not REQUIRED_ROLES.issubset(succeeded_roles)
        else []
    )
    event_types = {str(event["event_type"]) for event in events}
    if "PULL_REQUEST_CREATED" not in event_types and "PULL_REQUEST_UPDATED" not in event_types:
        problems.append("no persisted PR publication event")
    if (
        task.get("state") in {"READY_TO_MERGE", "MERGED"}
        and "TASK_READY_TO_MERGE" not in event_types
    ):
        problems.append("no persisted READY_TO_MERGE gate decision")
    gate_events = [event for event in events if event.get("event_type") == "TASK_READY_TO_MERGE"]
    gate_revision = gate_events[-1].get("payload", {}).get("revision") if gate_events else None
    revision = gate_revision if task.get("state") == "MERGED" else task.get("current_revision")
    current = [item for item in validations if item.get("revision") == revision]
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for item in current:
        latest.setdefault((str(item.get("kind")), str(item.get("name"))), item)
    checks = [
        item for item in latest.values() if item.get("kind") in {"CHECK", "CHECK_SUITE", "STATUS"}
    ]
    if not revision:
        problems.append("task has no current revision")
    if not checks:
        problems.append("no GitHub check evidence for current revision")
    elif any(str(item.get("status")) not in SUCCESSFUL_CHECKS for item in checks):
        problems.append("current revision has pending or failing GitHub checks")
    if any(str(item.get("status")) in BLOCKING_VALIDATIONS for item in latest.values()):
        problems.append("current revision has blocking GitHub evidence")
    if any(item.get("status") == "OPEN" for item in findings):
        problems.append("unresolved internal review findings remain")
    if require_repair and not any(str(job.get("action", "")).startswith("REPAIR_") for job in jobs):
        problems.append("no repair job observed")
    return problems


def validate_preflight(base_url: str) -> list[str]:
    problems: list[str] = []
    integrations = request(base_url, "/integrations")
    connected = {
        item.get("provider_name") for item in integrations if item.get("status") == "CONNECTED"
    }
    for required in ("github", "linear"):
        if required not in connected:
            problems.append(f"{required} integration is not CONNECTED")
    agents = request(base_url, "/agents")
    ready_roles = {item.get("role") for item in agents if item.get("status") == "READY"}
    missing_roles = REQUIRED_ROLES - ready_roles
    if missing_roles:
        problems.append(f"agents not ready: {', '.join(sorted(missing_roles))}")
    repositories = request(base_url, "/repositories")
    if not any(
        item.get("enabled") and item.get("index_status") == "READY" for item in repositories
    ):
        problems.append("no enabled repository has a READY knowledge index")
    workers = request(base_url, "/workers")
    if not any(item.get("online") for item in workers):
        problems.append("no scheduler worker is online")
    webhook_health = request(base_url, "/webhook-health")
    unhealthy = [item.get("provider") for item in webhook_health if item.get("failed", 0) > 0]
    if unhealthy:
        problems.append(f"failed webhook deliveries exist: {', '.join(map(str, unhealthy))}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a real Linear-to-GitHub workflow using persisted API evidence."
    )
    parser.add_argument("task_key", help="Linear issue identifier, for example CIT-531")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=3)
    parser.add_argument("--merge", action="store_true", help="Merge once READY_TO_MERGE")
    parser.add_argument("--require-repair", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()
    if not args.skip_preflight:
        preflight_problems = validate_preflight(args.base_url)
        if preflight_problems:
            print("preflight failed:", file=sys.stderr)
            for problem in preflight_problems:
                print(f"- {problem}", file=sys.stderr)
            return 1
    deadline = time.monotonic() + args.timeout
    task: dict[str, Any] | None = None
    previous_state = ""
    while time.monotonic() < deadline:
        task = find_task(args.base_url, args.task_key)
        if task is None:
            print(f"waiting for Linear task {args.task_key} ...", flush=True)
            time.sleep(args.poll_seconds)
            continue
        state = str(task["state"])
        if state != previous_state:
            print(f"{args.task_key}: {state}", flush=True)
            previous_state = state
        if state in TERMINAL_FAILURES:
            print(f"workflow stopped in {state}; inspect {task['id']}", file=sys.stderr)
            return 1
        if state == "READY_TO_MERGE":
            if not args.merge:
                print("pre-merge workflow validated; rerun with --merge to validate completion")
                break
            request(args.base_url, f"/tasks/{task['id']}/merge", method="POST")
        if state == "MERGED":
            break
        time.sleep(args.poll_seconds)
    else:
        print(f"timed out after {args.timeout}s", file=sys.stderr)
        return 1
    task_id = str(task["id"])
    jobs = request(args.base_url, f"/tasks/{task_id}/jobs")
    events = request(args.base_url, f"/tasks/{task_id}/events")
    validations = request(args.base_url, f"/tasks/{task_id}/validations")
    findings = request(args.base_url, f"/tasks/{task_id}/findings")
    problems = validate_history(task, jobs, events, validations, findings, args.require_repair)
    if task["state"] == "MERGED":
        event_types = {str(event["event_type"]) for event in events}
        if "LINEAR_READY_FOR_TESTING" not in event_types:
            problems.append("merge completed without confirmed Linear Ready for Testing event")
    if problems:
        print("validation failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"validated {args.task_key}: {len(jobs)} jobs, {len(events)} persisted events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
