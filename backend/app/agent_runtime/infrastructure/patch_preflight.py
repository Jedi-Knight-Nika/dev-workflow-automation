"""Read-only availability checks for the existing patch checker, not full validation."""

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

FORMAT_EXTENSIONS = frozenset(
    {
        ".html",
        ".css",
        ".scss",
        ".md",
        ".json",
        ".yaml",
        ".yml",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".svelte",
    }
)


class PatchRuntimeUnavailable(ValueError):
    """Known missing checker capabilities; never recover by buying another model call."""


def require_patch_runtime(packet: dict[str, Any]) -> None:
    preflight = packet.get("preflight", {})
    if preflight.get("ready") is False:
        raise PatchRuntimeUnavailable(
            "Patch runtime unavailable: " + ", ".join(preflight["missing_tools"])
        )


def patch_preflight(workspace: Path, paths: list[str]) -> dict[str, Any]:
    """Check executables before a paid patch; never install packages or execute repo code."""
    required = {"git"}
    local = set()
    frontend = any(p.startswith("frontend/src/") for p in paths)
    suffixes = {Path(p).suffix for p in paths}
    if frontend or suffixes & FORMAT_EXTENSIONS:
        required.add("node")
        local.add("prettier")
    if frontend:
        required.add("npm")
        local.add("eslint")
    if ".rs" in suffixes:
        required.add("rustfmt")
    if ".sh" in suffixes:
        required.add("sh")
    missing = sorted(name for name in required if shutil.which(name) is None)
    missing.extend(
        "frontend/node_modules/.bin/" + name
        for name in sorted(local)
        if not os.access(workspace / "frontend/node_modules/.bin" / name, os.X_OK)
    )
    if ".py" in suffixes and importlib.util.find_spec("ruff") is None:
        missing.append("python module ruff")
    return {
        "ready": not missing,
        "missing_tools": missing,
        "coverage": "Executable availability only; plugins, project configuration and runtime behavior remain unverified.",
    }
