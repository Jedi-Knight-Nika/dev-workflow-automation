"""Bounded, read-only access to current tracked source for engineering agents."""

import fnmatch
import json
from pathlib import Path, PurePosixPath
from typing import Any

from app.domain.security.paths import resolve_workspace_path
from app.infrastructure.git.workspaces import GitCommandError, run_git
from app.infrastructure.workers.executor import requested_file_context

REPOSITORY_TOOLS = (
    {
        "name": "read_repository_ranges",
        "description": "Read focused current source ranges, especially when full files exceed CONTEXT_LIMIT. Batch up to 10 related ranges. Line numbers start at 1; at most 200 lines per range. Returned next_line allows continuation.",
        "parameters": {
            "type": "object",
            "properties": {
                "ranges": {
                    "type": "array",
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "start_line": {"type": "integer", "minimum": 1},
                            "end_line": {"type": "integer", "minimum": 1},
                        },
                        "required": ["path", "start_line", "end_line"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["ranges"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_repository_snippets",
        "description": "Locate a symbol or literal text and return bounded matching lines with paths and line numbers. Use a narrow file glob such as backend/app/**/*.py, then batch read_repository_ranges around matches. Secret files are excluded.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 200},
                "pattern": {"type": "string"},
            },
            "required": ["query", "pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_repository_files",
        "description": "List current tracked file paths across the task repositories. Filter by glob and paginate with offset. Use these paths for reading files.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
            },
            "required": ["pattern", "offset"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_repository_files",
        "description": "Read complete current files. Batch related files in one call. Paths must be from list_repository_files, not stale RAG. Never request secrets.",
        "parameters": {
            "type": "object",
            "properties": {"paths": {"type": "array", "items": {"type": "string"}, "maxItems": 20}},
            "required": ["paths"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_repository",
        "description": "Find tracked files containing literal text, without loading their entire contents. Returns paths only; read matching files next.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "maxLength": 200}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },
)

CONSULTATION_TOOL = {
    "name": "ask_agent",
    "description": "Ask one allowed colleague a focused question you cannot resolve from repository evidence. This ends your turn; the orchestrator persists the question and resumes you after the reply. Never use this to delegate unrestricted work.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_node_id": {"type": "string"},
            "question": {"type": "string", "maxLength": 4000},
        },
        "required": ["target_node_id", "question"],
        "additionalProperties": False,
    },
}


def source_path_allowed(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return not any(
        part in {".git", ".worker-home", "node_modules", ".venv"}
        or part.startswith(".env")
        and part not in {".env.example", ".env.sample"}
        or part.lower().endswith((".pem", ".key", ".p12", ".pfx"))
        for part in parts
    )


class RepositoryTools:
    def __init__(
        self,
        workspaces: list[tuple[str, Path]],
        max_calls: int,
        max_bytes: int = 300_000,
        consultants: set[str] | None = None,
    ) -> None:
        self.workspaces = workspaces
        self.max_calls = min(max_calls, 80)
        self.calls = 0
        self.remaining = max_bytes
        self.consultants = consultants or set()
        self.consultation: dict[str, str] | None = None
        self.read_paths: set[str] = set()
        self.repeated_reads = 0
        self.last_trace: dict[str, Any] = {}

    def begin_history(self) -> None:
        """A new provider conversation cannot reference an earlier discarded history."""
        self.read_paths.clear()
        self.repeated_reads = 0

    async def execute(self, name: str, arguments: str) -> str:
        output = await self._execute_read(name, arguments)
        parsed = json.loads(output)
        rows = parsed if isinstance(parsed, list) else [parsed]
        # Persist status/size metadata, never source contents or arbitrary command arguments.
        self.last_trace = {
            "tool": name,
            "output_bytes": len(output.encode()),
            "remaining_source_bytes": self.remaining,
            "results": [
                {
                    key: row[key]
                    for key in ("path", "status", "start_line", "end_line", "next_line")
                    if key in row
                }
                for row in rows[:20]
                if isinstance(row, dict)
            ],
            "error": isinstance(parsed, dict) and "error" in parsed,
        }
        return output

    def _source_path(self, requested: str) -> tuple[Path, str]:
        candidate = PurePosixPath(requested)
        if candidate.is_absolute() or ".." in candidate.parts or not source_path_allowed(requested):
            raise ValueError("Use a non-secret relative source path")
        for prefix, workspace in self.workspaces:
            if len(self.workspaces) == 1 or requested.startswith(prefix + "/"):
                relative = requested if len(self.workspaces) == 1 else requested[len(prefix) + 1 :]
                path = resolve_workspace_path(workspace, relative, must_exist=True)
                if (
                    not source_path_allowed(path.relative_to(workspace.resolve()).as_posix())
                    or not path.is_file()
                ):
                    raise ValueError("Not a readable source file")
                return workspace, relative
        raise ValueError("Unknown repository prefix")

    async def _read_ranges(self, ranges: Any) -> list[dict[str, Any]]:
        if not isinstance(ranges, list) or not 1 <= len(ranges) <= 10:
            raise ValueError("Provide 1–10 source ranges")
        results = []
        for item in ranges:
            requested = item.get("path") if isinstance(item, dict) else None
            try:
                if not isinstance(requested, str):
                    raise TypeError("Range path must be a string")
                start, end = item.get("start_line"), item.get("end_line")
                if (
                    type(start) is not int
                    or type(end) is not int
                    or start < 1
                    or not start <= end < start + 200
                ):
                    raise ValueError(
                        "Use a range of at most 200 lines, starting at line 1 or later"
                    )
                workspace, relative = self._source_path(requested)
                tracked = (await run_git("ls-files", cwd=workspace)).splitlines()
                if relative not in tracked:
                    raise ValueError("Source path is not tracked")
                path = resolve_workspace_path(workspace, relative, must_exist=True)
                if path.stat().st_size > 1_000_000:
                    raise ValueError("Source file exceeds 1 MB")
                lines = []
                used = 0
                next_line = None
                with path.open(encoding="utf-8") as source:
                    for number, line in enumerate(source, 1):
                        if number < start:
                            continue
                        if number > end or used + len(line.encode()) > min(self.remaining, 12_000):
                            next_line = number
                            break
                        lines.append(line)
                        used += len(line.encode())
                self.remaining -= used
                results.append(
                    {
                        "path": requested,
                        "status": "LOADED_RANGE" if lines else "NO_LINES_WITHIN_BUDGET",
                        "start_line": start,
                        "end_line": start + len(lines) - 1,
                        "next_line": next_line,
                        "content": "".join(lines),
                    }
                )
            except (ValueError, TypeError, OSError, PermissionError) as exc:
                results.append(
                    {"path": requested, "status": "NOT_READABLE", "reason": str(exc)[:200]}
                )
        return results

    async def _execute_read(self, name: str, arguments: str) -> str:
        self.calls += 1
        if self.calls > self.max_calls:
            raise RuntimeError("Repository tool-call budget exhausted")
        try:
            args = json.loads(arguments)
            if not isinstance(args, dict):
                raise TypeError("Tool arguments must be an object")
            if name == "read_repository_ranges":
                result: Any = await self._read_ranges(args.get("ranges"))
            elif name == "search_repository_snippets":
                query, pattern = args.get("query"), args.get("pattern")
                if (
                    not isinstance(query, str)
                    or not 1 <= len(query) <= 200
                    or not isinstance(pattern, str)
                ):
                    raise ValueError("Provide a literal query and file glob")
                result = []
                for prefix, workspace in self.workspaces:
                    try:
                        output = await run_git(
                            "grep",
                            "-n",
                            "-I",
                            "-F",
                            "-m",
                            "3",
                            "-e",
                            query,
                            "--",
                            pattern,
                            cwd=workspace,
                        )
                    except GitCommandError as exc:
                        if str(exc).strip():
                            raise RuntimeError(
                                "Repository search failed; check workspace health"
                            ) from exc
                        output = ""
                    for match in output.splitlines():
                        parts = match.split(":", 2)
                        if len(parts) != 3 or not parts[1].isdigit():
                            continue
                        path, line, content = parts
                        displayed = path if len(self.workspaces) == 1 else f"{prefix}/{path}"
                        try:
                            self._source_path(displayed)
                        except (ValueError, PermissionError, OSError):
                            continue
                        content = content[:300]
                        size = len(content.encode())
                        if len(result) >= 20 or size > self.remaining:
                            break
                        self.remaining -= size
                        result.append({"path": displayed, "line": int(line), "content": content})
            elif name == "ask_agent":
                target, question = args.get("target_node_id"), args.get("question")
                if (
                    target not in self.consultants
                    or not isinstance(question, str)
                    or not 1 <= len(question.strip()) <= 4000
                ):
                    raise ValueError("Choose an allowed recipient and a focused question")
                self.consultation = {"target_node_id": target, "question": question.strip()}
                result = {"status": "WAITING_FOR_AGENT"}
            elif name == "read_repository_files":
                paths = args.get("paths")
                if (
                    not isinstance(paths, list)
                    or not 1 <= len(paths) <= 20
                    or not all(isinstance(p, str) and source_path_allowed(p) for p in paths)
                ):
                    raise ValueError(
                        "Provide 1–20 tracked source paths; secret paths are unavailable"
                    )
                # Tools are read-only during this model session. Earlier successful
                # reads remain in tool history, so sending them again wastes input.
                fresh_paths = list(dict.fromkeys(p for p in paths if p not in self.read_paths))
                repeated = list(dict.fromkeys(p for p in paths if p in self.read_paths))
                self.repeated_reads = self.repeated_reads + 1 if not fresh_paths else 0
                result = await requested_file_context(
                    self.workspaces,
                    fresh_paths,
                    max_context_bytes=max(self.remaining, 0),
                    path_filter=source_path_allowed,
                )
                for item in result:
                    if item.get("status") == "CONTEXT_LIMIT":
                        item["reason"] = (
                            "Use read_repository_ranges for a focused section; do not repeat the whole-file request."
                        )
                self.remaining -= sum(len(item.get("content", "").encode()) for item in result)
                for item in result:
                    if item.get("status") == "LOADED":
                        self.read_paths.add(str(item.get("requested_path") or item.get("path")))
                result.extend(
                    {
                        "path": path,
                        "status": "ALREADY_READ",
                        "reason": "Use the complete file in earlier tool output.",
                    }
                    for path in repeated
                )
            elif name in {"list_repository_files", "search_repository"}:
                paths = []
                for prefix, workspace in self.workspaces:
                    if name == "search_repository":
                        query = args.get("query")
                        if not isinstance(query, str) or not 1 <= len(query) <= 200:
                            raise ValueError("Search requires 1–200 characters")
                        # git grep -l returns paths, not potentially secret matching lines.
                        try:
                            output = await run_git(
                                "grep", "-l", "-I", "-F", "-e", query, "--", cwd=workspace
                            )
                        except GitCommandError as exc:
                            if str(exc).strip():
                                raise RuntimeError(
                                    "Repository search failed; check workspace health"
                                ) from exc
                            output = ""  # git grep exits 1, without stderr, for no matches.
                    else:
                        output = await run_git("ls-files", cwd=workspace)
                    paths.extend(
                        p if len(self.workspaces) == 1 else f"{prefix}/{p}"
                        for p in output.splitlines()
                        if source_path_allowed(p)
                    )
                pattern = args.get("pattern", "*")
                offset = args.get("offset", 0)
                if not isinstance(pattern, str) or type(offset) is not int or offset < 0:
                    raise ValueError("Invalid pattern or offset")
                matches = sorted(p for p in paths if fnmatch.fnmatch(p, pattern))
                result = {
                    "paths": matches[offset : offset + 100],
                    "total": len(matches),
                    "next_offset": offset + 100 if offset + 100 < len(matches) else None,
                }
            else:
                raise ValueError("Unknown tool")
            return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError, PermissionError, OSError) as exc:
            return json.dumps({"error": str(exc)[:300], "retryable": False})
