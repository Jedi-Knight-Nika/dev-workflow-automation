"""One deterministic subject for generated commits and pull requests."""

import re

_CONVENTIONAL = re.compile(r"^(?P<prefix>[a-z]+(?:\([\w./-]{1,24}\))?!?):\s+(?P<subject>.+)$")


def publication_title(title: str) -> str:
    """Preserve explicit types/scopes; use chore when intent is unspecified.

    Never infer a release-impacting feat/fix or breaking change from free text.
    Both publication surfaces use Git's existing 72-character subject limit.
    """
    cleaned = " ".join("".join(c if c.isprintable() else " " for c in title).split())
    match = _CONVENTIONAL.fullmatch(cleaned)
    if match and len(match["prefix"]) <= 40:
        prefix, subject = match["prefix"], match["subject"]
    else:
        prefix, subject = "chore", cleaned or "update task"
    return f"{prefix}: {subject}"[:72].rstrip()
