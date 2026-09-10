"""Compact repair evidence shared by fast and adaptive patch execution."""

import json
import re
from typing import Any


def compact_failure(checks: dict[str, Any]) -> dict[str, Any]:
    return {
        "error": checks.get("error"),
        "checks": [
            {
                k: v
                for k, v in c.items()
                if k in {"name", "exit_code", "errors", "stdout_tail", "runtime_error"}
            }
            for c in checks.get("checks", [])
            if c.get("exit_code") != 0
        ],
    }


def integration_repair_paths(checks: dict[str, Any], paths: list[str]) -> list[str]:
    """Select only named failing files, never expand scope from model-generated commands."""
    evidence = json.dumps(compact_failure(checks), ensure_ascii=False)
    named = []
    for path in paths:
        # Check tools may report repository-relative or package-relative paths.
        # Match complete filenames, not suffixes of other files or extensions.
        aliases = [path, path.split("/", 1)[1]] if "/" in path else [path]
        pattern = r"(?<![\w./-])(?:\./)?(?:" + "|".join(map(re.escape, aliases)) + r")(?![\w./-])"
        if re.search(pattern, evidence):
            named.append(path)
    selected = named or paths
    return selected if len(selected) <= 3 else []
