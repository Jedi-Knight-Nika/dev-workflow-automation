"""Read-only observation of one fixed-lifecycle task. Never resumes, retries or merges."""

import argparse
import json
import sys
import time
import urllib.request
from typing import Any


def request(base_url: str, path: str) -> Any:
    with urllib.request.urlopen(base_url.rstrip("/") + "/api/v1" + path, timeout=15) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_key", help="Exact external key, or task UUID")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=15)
    args = parser.parse_args()
    if args.timeout <= 0 or not 5 <= args.poll_seconds <= 60:
        parser.error("Use a positive timeout and a 5–60 second poll interval")
    deadline, previous = time.monotonic() + args.timeout, None
    while time.monotonic() < deadline:
        tasks = request(args.base_url, "/tasks?limit=500")
        task = next(
            (row for row in tasks if args.task_key in (row["id"], row.get("external_key"))), None
        )
        if task is None:
            time.sleep(args.poll_seconds)
            continue
        state = (task["status"], task["stage"], task["wait_reason"])
        if state != previous:
            print(
                json.dumps(
                    {
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "task_id": task["id"],
                        "status": state[0],
                        "stage": state[1],
                        "wait_reason": state[2],
                    }
                ),
                flush=True,
            )
            previous = state
        if state[0] in {"MERGED", "FAILED", "CANCELLED", "PAUSED", "WAITING_HUMAN"}:
            prefix = "/tasks/" + task["id"]
            print(
                json.dumps(
                    {
                        "task": task,
                        "metrics": request(args.base_url, prefix + "/metrics"),
                        "runs": request(args.base_url, prefix + "/runs"),
                        "validations": request(args.base_url, prefix + "/validations"),
                        "events": request(args.base_url, prefix + "/events"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if state[0] == "MERGED" else 2
        time.sleep(args.poll_seconds)
    print("Observation timed out. The task was not changed.", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
