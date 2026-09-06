from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProgressFingerprint:
    head_sha: str | None
    plan_revision: str | None
    failing_tests: tuple[str, ...] = ()
    blocking_findings: tuple[str, ...] = ()
    changed_files_hash: str | None = None
    result_type: str | None = None
    tool_error: str | None = None


def progress_made(previous: ProgressFingerprint | None, current: ProgressFingerprint) -> bool:
    """Evidence changed materially; an agent's narrative is intentionally not considered."""
    if previous is None:
        return True
    return any(
        (
            current.head_sha != previous.head_sha,
            current.plan_revision != previous.plan_revision,
            set(current.failing_tests) < set(previous.failing_tests),
            set(current.blocking_findings) < set(previous.blocking_findings),
            current.changed_files_hash != previous.changed_files_hash,
            current.result_type != previous.result_type,
            current.tool_error != previous.tool_error,
        )
    )
