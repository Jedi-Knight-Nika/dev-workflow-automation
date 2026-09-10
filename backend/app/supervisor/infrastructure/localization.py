"""Bounded advisory filename hints; no source execution or content preload."""

import os
import re
from pathlib import Path


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
                return [
                    path for _, path in sorted(matches, key=lambda pair: (-pair[0], pair[1]))[:8]
                ]
            path = Path(root) / name
            if path.is_symlink():
                continue
            relative = str(path.relative_to(workspace))
            folded = relative.casefold()
            score = sum(word in folded for word in words)
            if score and len(relative) <= 240:
                matches.append((score, relative))
    return [path for _, path in sorted(matches, key=lambda pair: (-pair[0], pair[1]))[:8]]
