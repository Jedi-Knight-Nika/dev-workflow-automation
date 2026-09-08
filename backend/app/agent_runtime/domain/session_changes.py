"""Explicit native-session changes; never an automatic recovery/retry policy."""

from enum import StrEnum


class SessionChangeMode(StrEnum):
    KEEP_NATIVE = "keep_native"
    HANDOFF = "handoff"


def can_keep_native(
    old_harness: str, new_harness: str, old_provider: str, new_provider: str
) -> bool:
    # The pinned Codex SDK supports thread_resume(model=...). Do not assume a
    # portable conversation format or silently import one provider's transcript.
    return (old_harness, new_harness, old_provider, new_provider) == (
        "codex",
        "codex",
        "openai",
        "openai",
    )


def handoff_request(request: str, summary: str, note: str, feedback: str) -> str:
    result = (
        f"Current task:\n{request}\n\n"
        "The operator explicitly started a new native session on the existing checkout. "
        "Previous native history was retained, not imported. Inspect the checkout and verify "
        "the following handoff before continuing; do not discard existing work.\n"
        f"Operator note: {note}\nPrevious checkpoint (advisory):\n{summary[-4000:]}\n"
        f"Pending feedback:\n{feedback}"
    )
    if len(result) > 24000:
        raise ValueError(
            "Task and pending feedback exceed the handoff limit; shorten them explicitly"
        )
    return result
