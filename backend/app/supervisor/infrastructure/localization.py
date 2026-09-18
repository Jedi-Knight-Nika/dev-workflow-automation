"""Bounded repository inventory and entry-point evidence; no source execution."""

import os
import re
from collections import defaultdict, deque
from heapq import nsmallest
from pathlib import Path

from app.agent_runtime.infrastructure.source_paths import source_path


def repository_entrypoints(workspace: Path, paths: list[str]) -> list[dict[str, str]]:
    """Small source evidence for entry documents and manifests, never executable instructions."""
    selected = sorted(
        (p for p in paths if Path(p).suffix in {".html", ".toml", ".json"}),
        key=lambda p: (Path(p).suffix != ".html", p.count("/"), p),
    )
    result = []
    remaining = 6000
    for name in selected[:8]:
        with source_path(workspace, name).open("rb") as stream:
            raw = stream.read(min(1500, remaining))
        result.append({"path": name, "source_prefix": raw.decode(errors="replace")})
        remaining -= len(raw)
        if remaining <= 0:
            break
    return result


def repository_paths(workspace: Path) -> list[str]:
    """Bounded, area-balanced inventory for semantic selection, independent of ticket language."""
    groups: dict[str, list[str]] = defaultdict(list)
    scanned = 0
    for root, directories, files in os.walk(workspace, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if not name.startswith(".")
            and name not in {"node_modules", "dist", "build", "target", "vendor", "__pycache__"}
            and not (Path(root) / name).is_symlink()
        )
        for name in sorted(files):
            if scanned >= 4000:
                break
            scanned += 1
            path = Path(root) / name
            if path.is_symlink() or name.startswith("."):
                continue
            if path.suffix not in {
                ".html",
                ".css",
                ".scss",
                ".js",
                ".ts",
                ".tsx",
                ".jsx",
                ".svelte",
                ".py",
                ".rs",
                ".md",
                ".json",
                ".toml",
                ".yaml",
                ".yml",
                ".sh",
                ".sql",
            }:
                continue
            if name.endswith(("-lock.json", ".min.js")):
                continue
            relative = path.relative_to(workspace)
            if len(str(relative)) <= 240:
                groups[relative.parts[0]].append(str(relative))
        if scanned >= 4000:
            break
    queues = [
        deque(sorted(paths, key=lambda p: (p.count("/"), p))) for _, paths in sorted(groups.items())
    ]
    result: list[str] = []
    size = 0
    while queues and len(result) < 160:
        remaining = []
        for queue in queues:
            name = queue.popleft()
            if size + len(name.encode()) > 10000 or len(result) >= 160:
                return result
            result.append(name)
            size += len(name.encode())
            if queue:
                remaining.append(queue)
        queues = remaining
    return result


def candidate_paths(workspace: Path, objective: str) -> list[str]:
    words = set(re.findall(r"[\w]{4,}", objective.casefold()))
    if not words:
        return []
    matches: list[tuple[int, str]] = []
    scanned = 0
    for root, directories, files in os.walk(workspace, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if not name.startswith(".")
            and name not in {"node_modules", "dist", "build", "vendor", "__pycache__"}
            and not (Path(root) / name).is_symlink()
        )
        for name in sorted(files):
            scanned += 1
            if scanned > 4000:
                break
            path = Path(root) / name
            if path.is_symlink():
                continue
            relative = str(path.relative_to(workspace))
            folded = relative.casefold()
            score = sum(word in folded for word in words)
            if score and len(relative) <= 240:
                matches.append((score, relative))
        if scanned > 4000:
            break
    return [path for _, path in nsmallest(8, matches, key=lambda pair: (-pair[0], pair[1]))]
