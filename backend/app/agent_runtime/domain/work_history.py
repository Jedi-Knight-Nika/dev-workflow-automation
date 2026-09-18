"""Bounded execution-plan facts shared by receipt auditing and read projections."""

import re
from typing import Any

STATUSES = frozenset({"PENDING", "RUNNING", "REPAIRING", "READY", "FAILED", "SUPERSEDED"})


def public_work_plans(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 6:
        return []
    result: list[dict[str, Any]] = []
    revisions: set[int] = set()
    for plan in value:
        if not isinstance(plan, dict) or type(plan.get("revision")) is not int:
            return []
        if plan["revision"] in revisions:
            return []
        revisions.add(plan["revision"])
        units = plan.get("units")
        if (
            not 0 <= plan["revision"] <= 6
            or not isinstance(units, list)
            or not 1 <= len(units) <= 6
        ):
            return []
        public = []
        seen: set[str] = set()
        for index, unit in enumerate(units):
            if not isinstance(unit, dict):
                return []
            id, dependencies, status = unit.get("id"), unit.get("depends_on"), unit.get("status")
            if (
                not isinstance(id, str)
                or not re.fullmatch(r"[a-z0-9_-]{1,60}", id)
                or id in seen
                or not isinstance(status, str)
                or status not in STATUSES
                or not isinstance(dependencies, list)
                or len(dependencies) > 5
                or any(type(item) is not int or not 0 <= item < index for item in dependencies)
            ):
                return []
            seen.add(id)
            public.append({"id": id, "depends_on": dependencies, "status": status})
        result.append({"revision": plan["revision"], "units": public})
    return result
