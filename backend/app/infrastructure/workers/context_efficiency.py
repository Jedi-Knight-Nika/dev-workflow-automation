"""Deterministic context selection; no extra model calls or hidden summarization."""

import json
import re
from pathlib import PurePosixPath
from typing import Any

from app.providers.base import ProviderRequest


def source_map(manifest: str, hint: str) -> dict[str, Any]:
    from app.infrastructure.workers.repository_tools import source_path_allowed

    paths = sorted(p for p in manifest.splitlines() if source_path_allowed(p))
    words = {w.lower().rstrip("s") for w in re.findall(r"[a-zA-Z][a-zA-Z_]{2,}", hint)}
    ranked = []
    for path in paths:
        names = {w.lower().rstrip("s") for w in re.findall(r"[a-zA-Z]{3,}", path)}
        score = 100 if path in hint else len(words & names)
        if score:
            ranked.append((-score, path))
    selected: list[str] = []
    used = 0
    for _, path in sorted(ranked):
        if used + len(path.encode()) > 4000 or len(selected) >= 40:
            break
        selected.append(path)
        used += len(path.encode())
    return {
        "candidate_paths": selected,
        "entrypoints": [
            p
            for p in paths
            if PurePosixPath(p).name in {"AGENTS.md", "package.json", "pyproject.toml", "Makefile"}
        ][:15],
        "guidance": "Paths verified in this checkout; relevance is heuristic, not source evidence. Read relevant ranges directly. Search only for missing symbols; do not enumerate the repository.",
    }


def compact_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve every check outcome, retaining useful failure tails rather than success logs."""
    result = []
    for check in checks:
        item = dict(check)
        output = item.get("output")
        if isinstance(output, str):
            limit = 200 if item.get("passed") else 2000
            item["output"] = (
                output if len(output) <= limit else "[earlier output omitted]\n" + output[-limit:]
            )
        result.append(item)
    return result


def request_token_reserve(request: ProviderRequest) -> int:
    """Conservative heuristic, not a provider tokenizer or billing estimate.

    Include schemas and history (including opaque reasoning) plus the full output
    allowance. Actual usage remains authoritative; provider overhead is not exact.
    """
    text = request.system + (request.cacheable_prompt_prefix or "") + request.prompt
    text += json.dumps(
        [request.tools, request.response_schema, request.tool_history], ensure_ascii=False
    )
    return (len(text.encode()) + 2) // 3 + 1024 + request.max_output_tokens


ROLE_PROTOCOLS = {
    "THINKER": "Inspect representative current contracts with batched range reads, not repeated listings. A file list is not source evidence. Write a concise plan: concrete paths, ordered changes, material risks and acceptance tests; state each requirement once. Do not rephrase the task in every section or demand a full-codebase audit. Delegate routine implementation details without inventing APIs.",
    "EXECUTOR": "Use candidate_paths and the plan to read only the next coherent change. Implement it, then test and correct it in this workspace. Do not enumerate the repository or load all target files at once. Batch independent reads or edits in one response; wait for results before dependent changes. Return only concise completion/evidence, not the plan again.",
    "DELIVERER": "Interpret the current event and select from the supplied repository candidates. Do not audit implementation or restate a technical plan. For delivery, act only on current PR evidence and authorized actions. Keep the summary concise and do not request another role for routine routing.",
    "INTAKE": "Classify the current event and repository scope once. Do not plan implementation or repeat historical blockers. Ask only for a genuinely missing product decision.",
    "REVIEWER": "Review the actual diff against acceptance criteria and open findings. Read surrounding source only for a concrete uncertainty. Report actionable findings with paths and evidence; do not replan or re-enumerate the repository. Never treat omitted diff or source as reviewed.",
    "TESTER": "Evaluate every supplied check outcome against acceptance criteria. Focus on failures and uncovered behavior; do not repeat successful logs or planning. Missing checks mean incomplete validation, not success. Distinguish environment failure from code failure.",
}
