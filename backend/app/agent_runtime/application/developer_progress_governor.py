"""Observes evidence; never reads source, edits code, or authorizes paid work."""

from dataclasses import asdict, dataclass, field
from time import monotonic
from typing import Any

from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy


@dataclass
class DeveloperProgressGovernor:
    policy: TokenEfficiencyPolicy
    total: int = 0
    last_progress: int = 0
    first_edit: int | None = None
    active_context: int | None = None
    peak_context: int | None = None
    diff_fingerprint: str | None = None
    warnings: set[str] = field(default_factory=set)
    repeats: dict[str, int] = field(default_factory=dict)
    stop_reason: str | None = None
    tool_calls: int = 0
    diff_changes: int = 0
    source_read_bytes: int = 0
    shell_output_bytes: int = 0
    repeated_read_count: int = 0
    reads: dict[str, int] = field(default_factory=dict)
    checks: dict[str, str] = field(default_factory=dict)
    check_improvements: int = 0
    started: float = field(default_factory=monotonic)
    first_tool_seconds: float | None = None
    first_edit_seconds: float | None = None
    source_read_count: int = 0
    compaction_count: int = 0
    phase: str = "DISCOVERY"
    failed_checks: dict[str, int] = field(default_factory=dict)
    inference_cycles: int = 0
    cached_input: int = 0

    def restore(self, snapshot: dict[str, Any]) -> None:
        self.total = int(snapshot.get("input_tokens_observed") or 0)
        self.first_edit = snapshot.get("tokens_to_first_edit")
        self.cached_input = int(snapshot.get("cached_input_tokens_observed") or 0)
        self.inference_cycles = int(snapshot.get("inference_cycle_count") or 0)
        self.last_progress = self.total - int(snapshot.get("tokens_since_last_progress") or 0)
        self.peak_context = snapshot.get("context_peak_tokens")
        self.diff_fingerprint = snapshot.get("diff_fingerprint")
        self.warnings = set(snapshot.get("warnings") or [])
        self.compaction_count = int(snapshot.get("compaction_count") or 0)

    def read(self, fingerprint: str, size: int) -> None:
        self.source_read_count += 1
        self.source_read_bytes += size
        self.reads[fingerprint] = self.reads.get(fingerprint, 0) + 1
        if self.reads[fingerprint] > 1:
            self.repeated_read_count += 1

    def check(self, command: str, outcome: str) -> None:
        self.phase = "TARGETED_VALIDATION" if outcome == "passed" else "DEBUGGING"
        previous = self.checks.get(command)
        if previous == outcome and outcome != "passed":
            self.failed_checks[command] = self.failed_checks.get(command, 1) + 1
        elif outcome != previous:
            self.failed_checks.pop(command, None)
        if previous is not None and outcome != previous:
            self.last_progress = self.total
            if outcome == "passed":
                self.check_improvements += 1
        self.checks[command] = outcome

    def progress(self, fingerprint: str) -> None:
        if fingerprint != self.diff_fingerprint:
            self.first_edit = self.total if self.first_edit is None else self.first_edit
            if self.first_edit_seconds is None:
                self.first_edit_seconds = monotonic() - self.started
            self.phase = "EDITING"
            self.diff_fingerprint = fingerprint
            self.last_progress = self.total
            self.diff_changes += 1
            self.repeats.clear()
            self.reads.clear()
            self.failed_checks.clear()

    def command(self, fingerprint: str, *, failed: bool, expensive: bool) -> None:
        self.tool_calls += 1
        if self.first_tool_seconds is None:
            self.first_tool_seconds = monotonic() - self.started
        if failed and expensive:
            self.repeats[fingerprint] = self.repeats.get(fingerprint, 0) + 1

    def observe(
        self,
        total: int,
        active_context: int | None,
        cached_input: int | None = None,
    ) -> tuple[list[str], str | None]:
        # Cumulative usage never resets when a native context compacts.
        self.total = max(self.total, total)
        self.inference_cycles += 1
        if cached_input is not None:
            self.cached_input += cached_input
        self.active_context = active_context
        if active_context is not None:
            self.peak_context = max(self.peak_context or 0, active_context)
        conditions = []
        stop = None
        if self.first_edit is None and self.total >= self.policy.first_edit_warning_tokens:
            conditions.append("EXPLORATION_WARNING")
            if self.total >= self.policy.exploration_hard_tokens:
                stop = "EXPLORATION_LIMIT"
        if self.total - self.last_progress >= self.policy.no_progress_tokens:
            conditions.append("NO_PROGRESS_WARNING")
            if self.total - self.last_progress >= self.policy.no_progress_tokens * 2:
                stop = "NO_PROGRESS"
        repeated = max(self.repeats.values(), default=0)
        if repeated >= self.policy.repeated_command_threshold:
            conditions.append("REPEATED_COMMAND_WARNING")
            if repeated > self.policy.repeated_command_threshold:
                stop = "REPEATED_TOOL_LOOP"
        if active_context is not None and active_context >= self.policy.active_context_soft_tokens:
            conditions.append("CONTEXT_WARNING")
            if active_context >= self.policy.active_context_hard_tokens:
                stop = "CONTEXT_HARD_LIMIT"
        if self.repeated_read_count >= 3 and self.source_read_bytes >= 40000:
            conditions.append("REPEATED_READ_WARNING")
        failures = max(self.failed_checks.values(), default=0)
        if failures >= self.policy.repeated_failure_threshold:
            conditions.append("UNCHANGED_VALIDATION_WARNING")
            if failures > self.policy.repeated_failure_threshold:
                stop = "REPEATED_TOOL_LOOP"
        if self.compaction_count > self.policy.max_compactions:
            conditions.append("REPEATED_COMPACTION_WARNING")
            if self.total - self.last_progress >= self.policy.no_progress_tokens:
                stop = "REPEATED_COMPACTION"
        fresh = sorted(set(conditions) - self.warnings)
        self.warnings.update(conditions)
        if self.policy.mode == "ENFORCE" and stop:
            self.stop_reason = stop
        return ([] if self.policy.mode == "INSTRUMENT" else fresh), self.stop_reason

    def snapshot(self) -> dict[str, Any]:
        return {
            "policy": asdict(self.policy),
            "input_tokens_observed": self.total,
            "cached_input_tokens_observed": self.cached_input,
            "uncached_input_tokens_observed": max(self.total - self.cached_input, 0),
            "inference_cycle_count": self.inference_cycles,
            "tokens_to_first_edit": self.first_edit,
            "active_context_estimate": self.active_context,
            "context_peak_tokens": self.peak_context,
            "tokens_since_last_progress": self.total - self.last_progress,
            "tool_call_count": self.tool_calls,
            "diff_changes": self.diff_changes,
            "diff_fingerprint": self.diff_fingerprint,
            "source_read_bytes": self.source_read_bytes,
            "shell_output_bytes": self.shell_output_bytes,
            "repeated_read_count": self.repeated_read_count,
            "targeted_check_improvements": self.check_improvements,
            "source_read_count": self.source_read_count,
            "time_to_first_tool_seconds": self.first_tool_seconds,
            "time_to_first_edit_seconds": self.first_edit_seconds,
            "compaction_count": self.compaction_count,
            "phase_label": self.phase,
            "repeated_command_count": sum(max(0, n - 1) for n in self.repeats.values()),
            "warnings": sorted(self.warnings),
            "stop_reason": self.stop_reason,
            "measurement_quality": {
                "active_context": "last-inference-input-estimate",
                "progress": "native-events",
                "phase_attribution": "estimated",
                "tool_bytes": "native-exposed-output",
            },
        }
