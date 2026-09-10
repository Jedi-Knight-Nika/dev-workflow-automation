"""Bounded source compilation; hashes always cover complete current files."""

import hashlib
import heapq
import json
from pathlib import Path
from typing import Any

from app.agent_runtime.infrastructure.repo_index import extract, words
from app.agent_runtime.infrastructure.source_paths import source_path


def supervisor_annotations(prompt: str) -> dict[str, Any]:
    """Read additive guidance; malformed or absent annotations never replace the task."""
    marker = "Advisory Supervisor annotations"
    if marker not in prompt:
        return {}
    tail = prompt.rsplit(marker, 1)[1]
    start = tail.find("\n{")
    if start < 0:
        return {}
    try:
        value, _ = json.JSONDecoder().raw_decode(tail[start + 1 :])
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def compile_source(workspace: Path, name: str, objective: str, budget: int) -> dict[str, Any]:
    path = source_path(workspace, name)
    if not path.is_file() or path.stat().st_size > 300000:
        raise ValueError("Source is unavailable or exceeds bounded inspection: " + name)
    raw = path.read_bytes()
    text = raw.decode()
    result: dict[str, Any] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest()}
    lines = text.splitlines(keepends=True)
    if len(raw) <= budget:
        return {**result, "text": text, "start_line": 1, "end_line": len(lines), "complete": True}
    query = words(objective)
    metadata = extract(name, raw)
    ranked = heapq.nsmallest(
        8,
        ((-len(query & words(line)), index) for index, line in enumerate(lines)),
    )
    spans = [(0, min(35, len(lines)))]  # Imports and file-level interfaces.
    for score, index in ranked:
        if score == 0:
            continue
        symbol = next(
            (
                s
                for s in metadata["symbols"]
                if s["line"] <= index + 1 <= s["end"] and s["end"] - s["line"] <= 140
            ),
            None,
        )
        spans.append(
            (symbol["line"] - 1, symbol["end"])
            if symbol
            else (max(0, index - 12), min(len(lines), index + 45))
        )
    selected: set[int] = set()
    remaining = budget
    for start, end in spans:
        indexes = set(range(start, end)) - selected
        size = sum(len(lines[i].encode()) for i in indexes)
        if size <= remaining:
            selected.update(indexes)
            remaining -= size
    if not selected:
        raise ValueError("Source has no complete ranges within the packet budget: " + name)
    ranges = []
    ordered = sorted(selected)
    start = previous = ordered[0]
    for index in [*ordered[1:], len(lines) + 1]:
        if index != previous + 1:
            ranges.append(
                {
                    "start_line": start + 1,
                    "end_line": previous + 1,
                    "text": "".join(lines[start : previous + 1]),
                    "reason": "Task-matched code or file-level imports/interfaces",
                }
            )
            start = index
        previous = index
    return {
        **result,
        "ranges": ranges,
        "complete": False,
        "note": "Omitted lines are unknown, not empty. Patch only evidenced hunks; request re-planning if insufficient.",
    }
