"""Bounded, read-only access to current tracked source for engineering agents."""

import fnmatch
import json
from pathlib import Path, PurePosixPath
from typing import Any

from app.infrastructure.git.workspaces import GitCommandError, run_git
from app.infrastructure.workers.executor import requested_file_context

REPOSITORY_TOOLS = (
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

    def begin_history(self) -> None:
        """A new provider conversation cannot reference an earlier discarded history."""
        self.read_paths.clear()
        self.repeated_reads = 0

    async def execute(self, name: str, arguments: str) -> str:
        self.calls += 1
        if self.calls > self.max_calls:
            raise RuntimeError("Repository tool-call budget exhausted")
        try:
            args = json.loads(arguments)
            if not isinstance(args, dict):
                raise TypeError("Tool arguments must be an object")
            if name == "ask_agent":
                target, question = args.get("target_node_id"), args.get("question")
                if (
                    target not in self.consultants
                    or not isinstance(question, str)
                    or not 1 <= len(question.strip()) <= 4000
                ):
                    raise ValueError("Choose an allowed recipient and a focused question")
                self.consultation = {"target_node_id": target, "question": question.strip()}
                result: Any = {"status": "WAITING_FOR_AGENT"}
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
