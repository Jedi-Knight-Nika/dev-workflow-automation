"""One deterministic subject for generated commits and pull requests."""

import re

_CONVENTIONAL = re.compile(r"^(?P<prefix>[a-z]+(?:\([\w./-]{1,24}\))?!?):\s+(?P<subject>.+)$")
_TYPES = {
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
}


def english_summary(summary: str) -> list[str]:
    return [
        line.strip().lstrip("-* ")
        for line in summary.splitlines()
        if line.strip()
        and line.strip() not in {"IMPLEMENTED", "MILESTONE_COMPLETE", "NEEDS_PLAN"}
        and all(not c.isalpha() or "a" <= c.lower() <= "z" for c in line)
        and not line.startswith("Deterministic ")
    ][:12]


def publication_title(title: str, summary: str = "") -> str:
    """Preserve explicit types/scopes; use chore when intent is unspecified.

    Never infer a release-impacting feat/fix or breaking change from free text.
    Both publication surfaces use Git's existing 72-character subject limit.
    """
    candidates = english_summary(summary)
    conventional = next((s for s in candidates if _CONVENTIONAL.fullmatch(s)), None)
    source = conventional or title
    if not all(not c.isalpha() or "a" <= c.lower() <= "z" for c in source):
        source = next(iter(candidates), "update task implementation")
    cleaned = " ".join("".join(c if c.isprintable() else " " for c in source).split())
    match = _CONVENTIONAL.fullmatch(cleaned)
    if match and len(match["prefix"]) <= 40 and re.split(r"[(!]", match["prefix"])[0] in _TYPES:
        prefix, subject = match["prefix"], match["subject"]
    else:
        prefix, subject = "chore", cleaned or "update task"
    return f"{prefix}: {subject}"[:72].rstrip()


def publication_body(
    *,
    task_ref: str,
    title: str,
    summary: str,
    sha: str,
    change_context: str = "",
    checks: list[list[str]] | None = None,
) -> str:
    details = english_summary(summary)
    details = [s for s in details if not _CONVENTIONAL.fullmatch(s)]
    description = (
        "\n".join(f"- {s}" for s in details) or f"- {title.split(': ', 1)[-1].capitalize()}."
    )
    commands = "\n".join(f"- `{' '.join(command)}` — passed" for command in (checks or []))
    changed = (
        f"\n## Changed files\n\n```text\n{change_context[:6000]}\n```\n" if change_context else ""
    )
    return (
        f"## Summary\n\n{description}\n\nTask: {task_ref}\n"
        + changed
        + f"\n## Validation\n\nFull deterministic validation passed at `{sha}`.\n{commands}\n"
        + "\n## Review\n\nGitHub CI and current-commit approval are checked separately before merge.\n"
    )
