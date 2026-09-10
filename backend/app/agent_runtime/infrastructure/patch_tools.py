"""Deterministic localization and atomic unified-patch application in the runner sandbox."""

import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.agent_runtime.infrastructure.patch_context import compile_source, supervisor_annotations
from app.agent_runtime.infrastructure.repo_index import EXTENSIONS, investigate
from app.agent_runtime.infrastructure.source_paths import source_path


def prepare(
    workspace: Path,
    objective: str,
    paths: list[str] | None = None,
    new_files: list[str] | None = None,
    work_objective: str = "",
) -> dict[str, Any]:
    if paths is not None and (
        not isinstance(paths, list)
        or not 1 <= len(paths) <= 3
        or any(not isinstance(path, str) for path in paths)
        or len(set(paths)) != len(paths)
    ):
        raise ValueError("Patch needs 1–3 distinct repository text files")
    new_files = new_files or []
    if (
        not isinstance(new_files, list)
        or any(not isinstance(path, str) for path in new_files)
        or len(set(new_files)) != len(new_files)
        or (new_files and (paths is None or not set(new_files) <= set(paths)))
    ):
        raise ValueError("New files require an explicit bounded work unit")
    # Rank using the user's words, not generic Supervisor implementation advice
    # or URL-encoded tracker metadata that can overwhelm the actual UI identifier.
    query = objective.split("Advisory Supervisor annotations", 1)[0]
    query = query.split("\n\nTrello:", 1)[0]
    if work_objective:
        query = work_objective + "\n" + query
    hints = []
    if paths is None:
        hints = supervisor_annotations(objective).get("target_paths", [])
        if (
            not isinstance(hints, list)
            or len(hints) > 3
            or any(not isinstance(p, str) for p in hints)
        ):
            raise ValueError("Invalid Supervisor source selection")
    # Compile bounded source separately, using complete current-file hashes.
    mapped = investigate(workspace, query[:6000], include_source_slices=False)
    selected = paths if paths is not None else hints or mapped["candidate_paths"]
    if paths is None and selected and Path(selected[0]).suffix == ".html":
        target = source_path(workspace, selected[0])
        related = []
        for reference in re.findall(r'(?:href|src)=["\']([^"\']+)["\']', target.read_text()):
            if ":" in reference or "?" in reference or "#" in reference:
                continue
            name = str((target.parent / reference.lstrip("/")).relative_to(workspace))
            candidate = source_path(workspace, name)
            if candidate.is_file() and candidate.suffix in {".css", ".js", ".ts"}:
                related.append(name)
        selected = list(dict.fromkeys([selected[0], *related, *selected[1:]]))
    if not selected:
        raise ValueError("Patch MVP needs 1–3 localized repository text files")
    sources: list[dict[str, Any]] = []
    source_bytes = 0
    for name in selected:
        path = source_path(workspace, name)
        if name in new_files:
            if path.exists() or not path.parent.is_dir() or path.suffix not in EXTENSIONS:
                raise ValueError(
                    "New text files must be absent and use an existing source directory"
                )
            sources.append({"path": name, "sha256": "MISSING", "text": "", "new_file": True})
            continue
        size = path.stat().st_size
        if size > 24000 or source_bytes + size > 36000:
            if paths is not None or not sources:
                compiled = compile_source(
                    workspace, name, query, min(10000, max(0, 34000 - source_bytes))
                )
                sources.append(compiled)
                source_bytes += len(json.dumps(compiled).encode())
                if len(sources) == 3:
                    break
                continue
            continue  # Optional related candidates must not block an in-budget target.
        content = path.read_bytes()
        sources.append(
            {"path": name, "sha256": hashlib.sha256(content).hexdigest(), "text": content.decode()}
        )
        source_bytes += len(content)
        if len(sources) == 3:
            break
    if source_bytes > 36000:
        raise ValueError("Localized source exceeds patch packet budget; split the work unit")
    return {"repo_map": mapped["repo_map"], "sources": sources, "sha": mapped["sha"]}


def normalize_file_boundaries(patch: str) -> str:
    """Make plain unified multi-file patches unambiguous to git --recount.

    Preserve every hunk byte; never fuzzy-match or alter source context.
    Already Git-formatted patches retain their existing boundaries.
    """
    if any(line.startswith("diff --git ") for line in patch.splitlines()):
        return patch
    patch = (
        re.sub(
            r"^--- /dev/null\n\+\+\+ b/([^\n]+)\n",
            lambda match: (
                "diff --git "
                + json.dumps("a/" + match[1])
                + " "
                + json.dumps("b/" + match[1])
                + "\nnew file mode 100644\n"
                + match[0]
            ),
            patch,
            flags=re.MULTILINE,
        )
        if "--- /dev/null" in patch
        else patch
    )
    return re.sub(
        r"^--- a/([^\n]+)\n\+\+\+ b/\1\n",
        lambda match: (
            "diff --git "
            + json.dumps("a/" + match[1])
            + " "
            + json.dumps("b/" + match[1])
            + "\n"
            + match[0]
        ),
        patch,
        flags=re.MULTILINE,
    )


def apply(workspace: Path, patch: str, hashes: dict[str, str]) -> list[str]:
    if not patch or len(patch.encode()) > 32000 or "\x00" in patch:
        raise ValueError("Empty or oversized unified patch")
    lines = patch.splitlines()
    if any(
        line.startswith(
            (
                "old mode ",
                "new mode ",
                "deleted file mode ",
                "rename ",
                "copy ",
                "GIT binary patch",
                "Binary files",
            )
        )
        for line in lines
    ):
        raise ValueError(
            "Patch only changes admitted text files; no modes, renames or binary changes"
        )
    if any(line.startswith("new file mode ") and line != "new file mode 100644" for line in lines):
        raise ValueError("New files must be regular non-executable text files")
    for line in lines:
        if line.startswith(("--- ", "+++ ")):
            prefix = "a/" if line.startswith("--- ") else "b/"
            name = line[4:]
            if line.startswith("--- ") and name == "/dev/null":
                continue  # The numstat target below still requires an explicit MISSING precondition.
            if not name.startswith(prefix) or name[2:] not in hashes:
                raise ValueError("Patch header is outside the localized files")
    patch = normalize_file_boundaries(patch)
    patch_bytes = patch.encode()
    env = {
        "PATH": os.defpath,
        "HOME": "/tmp",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }

    def git(*args: str) -> bytes:
        result = subprocess.run(
            [
                "git",
                "-c",
                "safe.directory=" + str(workspace.resolve()),
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "apply",
                *args,
            ],
            input=patch_bytes,
            cwd=workspace,
            env=env,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if result.returncode:
            raise ValueError("Patch rejected: " + result.stderr.decode(errors="replace")[-2000:])
        return result.stdout

    rows = git("--recount", "--numstat", "-z").decode().split("\x00")
    changed = []
    for row in filter(None, rows):
        fields = row.split("\t", 2)
        if (
            len(fields) != 3
            or not fields[0].isdigit()
            or not fields[1].isdigit()
            or fields[2] not in hashes
        ):
            raise ValueError("Unsupported or out-of-scope patch target")
        name = fields[2]
        path = source_path(workspace, name)
        if hashes[name] == "MISSING":
            if path.exists() or not path.parent.is_dir():
                raise ValueError("New-file precondition failed; patch not applied")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise ValueError("Source changed since localization; patch not applied")
        changed.append(name)
    if not changed or len(changed) > 3:
        raise ValueError("Patch must modify 1–3 localized files")
    git("--recount", "--check", "--whitespace=nowarn")
    git(
        "--recount", "--whitespace=nowarn"
    )  # No --reject: check the entire patch before modifying files.
    return sorted(set(changed))


async def execute(workspace: Path, name: str, arguments: dict[str, Any]) -> Any:
    if name == "survey":
        from app.agent_runtime.infrastructure.repo_index import survey

        return survey(workspace, arguments["objective"])
    if name == "inspect":
        paths = arguments["paths"]
        if not isinstance(paths, list) or not 1 <= len(paths) <= 3:
            raise ValueError("Inspect 1–3 source files in one batch")
        return {
            "sources": [compile_source(workspace, p, arguments["objective"], 6000) for p in paths]
        }
    if name == "prepare":
        return prepare(
            workspace,
            arguments["objective"],
            arguments.get("paths"),
            arguments.get("new_files"),
            arguments.get("work_objective", ""),
        )
    if name == "apply":
        return {"changed_files": apply(workspace, arguments["patch"], arguments["hashes"])}
    if name == "check":
        from app.agent_runtime.infrastructure.patch_checks import check_repository

        return await check_repository(
            workspace, arguments["paths"], intermediate=arguments.get("intermediate", False)
        )
    raise ValueError("Unknown patch operation")


if __name__ == "__main__":
    try:
        print(
            json.dumps(
                asyncio.run(execute(Path("/workspace"), sys.argv[1], json.loads(sys.argv[2]))),
                ensure_ascii=False,
            )
        )
    except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc)[:2200]}))
        raise SystemExit(1)
