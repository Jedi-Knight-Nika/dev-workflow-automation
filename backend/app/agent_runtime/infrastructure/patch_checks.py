"""File-scoped checks across repository areas, with no package installation."""

import sys
from pathlib import Path
from typing import Any

from app.agent_runtime.infrastructure.bounded_command import capture_command
from app.agent_runtime.infrastructure.repository_tools import check_frontend
from app.agent_runtime.infrastructure.source_paths import source_path


async def check_repository(workspace: Path, paths: list[str]) -> dict[str, Any]:
    if not paths or len(paths) > 3:
        raise ValueError("Check 1–3 localized files")
    for path in paths:
        source_path(workspace, path)
    frontend = [p for p in paths if p.startswith("frontend/src/")]
    checks = []
    if frontend:
        checks.extend((await check_frontend(workspace, frontend))["checks"])
    commands = []
    others = [p for p in paths if p not in frontend]
    prettier = {
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
    formatted = ["./" + p for p in others if Path(p).suffix in prettier]
    if formatted:
        commands.append(
            (
                "format",
                [str(workspace / "frontend/node_modules/.bin/prettier"), "--write", *formatted],
            )
        )
    python = ["./" + p for p in others if Path(p).suffix == ".py"]
    if python:
        commands.extend(
            [
                ("python_format", [sys.executable, "-m", "ruff", "format", *python]),
                ("python_lint", [sys.executable, "-m", "ruff", "check", *python]),
            ]
        )
    for path in others:
        suffix = Path(path).suffix
        if suffix == ".rs":
            commands.append(("rust_format", ["rustfmt", "--check", "./" + path]))
        elif suffix == ".sh":
            commands.append(("shell_syntax", ["sh", "-n", "./" + path]))
        elif suffix == ".toml":
            commands.append(
                (
                    "toml_syntax",
                    [
                        sys.executable,
                        "-c",
                        "import sys,tomllib; tomllib.load(open(sys.argv[1],'rb'))",
                        "./" + path,
                    ],
                )
            )
    commands.append(
        ("diff_check", ["git", "-c", "safe.directory=" + str(workspace), "diff", "--check"])
    )
    for name, argv in commands:
        try:
            result = await capture_command(argv, cwd=workspace)
        except (OSError, TimeoutError) as exc:
            result = {
                "exit_code": -1,
                "runtime_error": True,
                "stdout_tail": f"{name} unavailable: {type(exc).__name__}",
            }
        result["stdout_tail"] = str(result.get("stdout_tail", ""))[-2400:]
        checks.append({"name": name, **result})
    return {
        "kind": "repository_checks",
        "paths": paths,
        "checks": checks,
        "exit_code": int(any(c["exit_code"] != 0 for c in checks)),
        "coverage": "Targeted formatting/syntax checks only; configured full validator remains required.",
    }
