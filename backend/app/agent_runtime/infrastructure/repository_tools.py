"""Small runner-local helpers. No credentials, network calls or AI inference."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.agent_runtime.infrastructure.bounded_command import capture_command, run
from app.agent_runtime.infrastructure.repo_index import investigate


def formatter_command(workspace: Path, paths: list[str]) -> tuple[Path, list[str]]:
    frontend = (workspace / "frontend").resolve()
    if not frontend.is_relative_to(workspace.resolve()):
        raise ValueError("Frontend must be inside the task workspace")
    executable = frontend / "node_modules/.bin/prettier"
    if not executable.is_file():
        raise ValueError(
            "Runtime missing installed frontend formatter; do not install dependencies"
        )
    if not paths or len(paths) > 20:
        raise ValueError("Provide 1–20 checkout-relative frontend file paths")
    relative = []
    for name in paths:
        path = (workspace / name).resolve()
        if not path.is_relative_to(frontend) or not path.is_file() or "node_modules" in path.parts:
            raise ValueError("Formatter target must be a frontend source/config file")
        relative.append("./" + str(path.relative_to(frontend)))
    return frontend, [str(executable), "--write", *relative]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["investigate", "format", "lint", "check"])
    parser.add_argument("arguments", nargs="+")
    args = parser.parse_args()
    workspace = Path("/workspace")
    if args.operation == "investigate":
        print(json.dumps(investigate(workspace, " ".join(args.arguments)), ensure_ascii=False))
    elif args.operation == "check":
        result = asyncio.run(check_frontend(workspace, args.arguments))
        print(json.dumps(result))
        raise SystemExit(result["exit_code"])
    else:
        cwd, argv = formatter_command(workspace, args.arguments)
        if args.operation == "lint":
            argv = [str(cwd / "node_modules/.bin/eslint"), *argv[2:]]
        raise SystemExit(asyncio.run(run(argv, cwd=cwd)))


def lint_evidence(workspace: Path, result: dict[str, Any]) -> dict[str, Any]:
    """Parse complete ESLint output; partial or malformed evidence authorizes nothing."""
    if result.get("truncated"):
        return {}
    try:
        reports = json.loads(result["stdout_tail"])
        root = workspace.resolve()
        errors = [
            {
                "path": str(Path(report["filePath"]).relative_to(root)),
                "line": message.get("line"),
                "rule": message.get("ruleId"),
                "message": str(message["message"])[:240],
            }
            for report in reports
            for message in report["messages"]
            if message.get("severity") == 2
        ]
        return {"errors": errors[:6], "error_count": len(errors)}
    except (AttributeError, KeyError, TypeError, ValueError):
        return {}


async def check_frontend(
    workspace: Path, paths: list[str], *, typecheck: bool = True
) -> dict[str, Any]:
    """Format selected files, then typecheck + file-scoped lint in one model round trip.

    Type checking remains project-wide because Svelte imports cross file boundaries.
    This is developer feedback, never a replacement for authoritative validation.
    """
    cwd, formatter = formatter_command(workspace, paths)
    commands = {
        "format": formatter,
        "typecheck": ["npm", "run", "typecheck"],
        "lint": [str(cwd / "node_modules/.bin/eslint"), "--format", "json", *formatter[2:]],
    }

    async def check(name: str) -> dict[str, Any]:
        try:
            result = await capture_command(commands[name], cwd=cwd)
        except (OSError, TimeoutError) as exc:
            result = {"exit_code": -1, "stdout_tail": str(exc)[-500:], "runtime_error": True}
        if name == "lint":
            result.update(lint_evidence(workspace, result))
        cap = 2400 if result["exit_code"] else 400
        output = str(result.get("stdout_tail", ""))
        result["truncated"] = result.get("truncated", False) or len(output.encode()) > cap
        result["stdout_tail"] = output.encode()[-cap:].decode(errors="replace")
        return {"name": name, **result}

    formatted = await check("format")
    # Do not run tools concurrently with the formatter modifying their input files.
    names = ["typecheck", "lint"] if typecheck else ["lint"]
    results = [formatted, *await asyncio.gather(*(check(name) for name in names))]
    return {
        "kind": "frontend_checks",
        "paths": paths,
        "exit_code": 1 if any(item["exit_code"] != 0 for item in results) else 0,
        "checks": results,
    }


if __name__ == "__main__":
    main()
