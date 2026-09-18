"""Deterministic validation evidence and bounded repair feedback."""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    command: tuple[str, ...]
    exit_code: int | None
    output_tail: str
    timed_out: bool = False
    started_at: str | None = None
    finished_at: str | None = None

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    head_sha: str
    fingerprint: str
    checks: tuple[CheckResult, ...]
    change_context: str | None = ""

    def progress_count(self, previous_fingerprint: object, previous_count: int) -> int:
        if not self.passed and previous_fingerprint == self.fingerprint:
            return previous_count + 1
        return 0

    def repair_feedback(self) -> str:
        failures = [
            {
                "command": check.command,
                "exit_code": check.exit_code,
                "timed_out": check.timed_out,
                "output_tail": check.output_tail[-1000:],
            }
            for check in self.checks
            if not check.passed
        ]
        return (
            "Fix these deterministic validation failures. Full logs remain in validation evidence:\n"
            + json.dumps(failures)[:8000]
        )
