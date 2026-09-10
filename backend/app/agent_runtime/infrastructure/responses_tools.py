"""Bounded compound tool surface for the Responses harness.

This module executes inside the existing Codex OS sandbox, without a model turn.
It exposes neither arbitrary shell execution nor access outside the checkout.
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from app.agent_runtime.infrastructure.repo_index import investigate
from app.agent_runtime.infrastructure.repository_tools import check_frontend
from app.agent_runtime.infrastructure.source_paths import source_path


def inspect_ranges(workspace: Path, ranges: Any) -> list[dict[str, Any]]:
    """Read one source snapshot per file within a bounded inspection call."""
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 3:
        raise ValueError("Inspect 1–3 relevant ranges together")
    for item in ranges:
        start, end = item["start"], item["end"]
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= start + 199:
            raise ValueError("Use a 1-based range of at most 200 lines")
    result = []
    remaining = 12000
    snapshots: dict[Path, tuple[str, list[bytes]]] = {}
    for item in ranges:
        path = source_path(workspace, item["path"])
        if path not in snapshots:
            if path.stat().st_size > 1_000_000:
                raise ValueError("Source file exceeds the read size limit")
            content = path.read_bytes()
            snapshots[path] = hashlib.sha256(content).hexdigest(), content.splitlines()
        digest, lines = snapshots[path]
        start, end = item["start"], item["end"]
        selected = b"\n".join(lines[start - 1 : end])
        shown = selected[:remaining]
        remaining -= len(shown)
        result.append(
            {
                "path": item["path"],
                "sha256": digest,
                "start": start,
                "end": end,
                "text": shown.decode("utf-8", errors="replace"),
                "truncated": len(shown) < len(selected),
            }
        )
    return result


async def execute_tool(workspace: Path, name: str, arguments: dict[str, Any]) -> Any:
    if name == "repo_investigate":
        return investigate(workspace, str(arguments["objective"])[:4000])
    if name == "inspect_ranges":
        return inspect_ranges(workspace, arguments["ranges"])
    if name == "edit_file":
        path = source_path(workspace, arguments["path"])
        old, new = arguments["old_text"], arguments["new_text"]
        if not isinstance(old, str) or not isinstance(new, str) or len(new.encode()) > 24000:
            raise ValueError("Invalid or oversized edit")
        expected = arguments["sha256"]
        if not path.exists():
            if expected != "NEW" or old:
                raise ValueError("New files require sha256 NEW and empty old_text")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x") as target:
                target.write(new)
        else:
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("File changed; inspect the relevant current range before editing")
            text = content.decode()
            if not old or text.count(old) != 1:
                raise ValueError("old_text must match exactly one source range")
            path.write_text(text.replace(old, new, 1))
        return {
            "edited": arguments["path"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    if name == "run_developer_checks":
        paths = arguments["paths"]
        if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
            raise ValueError("Supply all changed frontend paths")
        for path in paths:
            source_path(workspace, path)
        return await check_frontend(workspace, paths)
    raise ValueError("Unknown tool")


def schema(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOLS = [
    schema(
        "repo_investigate",
        "Locate relevant files, symbols, tests and source slices in one operation.",
        {"objective": {"type": "string"}},
    ),
    schema(
        "inspect_ranges",
        "Read up to three relevant source ranges together; returns current file hashes.",
        {
            "ranges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "path": {"type": "string"},
                        "start": {"type": "integer"},
                        "end": {"type": "integer"},
                    },
                    "required": ["path", "start", "end"],
                },
            }
        },
    ),
    schema(
        "edit_file",
        "Replace one exact unique source range. Use current file sha256. For a new file use NEW and empty old_text.",
        {field: {"type": "string"} for field in ("path", "sha256", "old_text", "new_text")},
    ),
    schema(
        "run_developer_checks",
        "Format changed frontend files, then typecheck and lint. Waits internally and returns all results together. No polling needed.",
        {"paths": {"type": "array", "items": {"type": "string"}}},
    ),
]


if __name__ == "__main__":
    try:
        result = asyncio.run(execute_tool(Path("/workspace"), sys.argv[1], json.loads(sys.argv[2])))
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)[:500]}))
        raise SystemExit(1)
