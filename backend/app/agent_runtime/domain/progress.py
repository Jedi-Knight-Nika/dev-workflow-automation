"""Explicit progress evidence. Classification alone never authorizes spending."""

from dataclasses import asdict, dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ProgressWindow:
    input_tokens: int
    uncached_input_tokens: int | None
    diff_changed: bool = False
    checks_improved: bool = False
    checks_regressed: bool = False
    milestone_advanced: bool = False
    new_localization: bool = False
    repeated_commands: int = 0
    repeated_failures: int = 0
    repeated_reads: int = 0

    def classify(self) -> Literal["PRODUCTIVE", "MARGINAL", "STALLED", "REGRESSING"]:
        if self.checks_regressed and not self.checks_improved:
            return "REGRESSING"
        if self.checks_improved or self.milestone_advanced or self.new_localization:
            return "PRODUCTIVE"
        if self.repeated_failures >= 2 or self.repeated_commands >= 2 or self.repeated_reads >= 3:
            return "STALLED"
        # A changed diff by itself does not prove that the solution improved.
        return "MARGINAL"

    def view(self) -> dict[str, Any]:
        state = self.classify()
        return {
            **asdict(self),
            "classification": state,
            "recommendation": {
                "PRODUCTIVE": "CONTINUE_WITHIN_BUDGET",
                "MARGINAL": "NARROW_CONTEXT",
                "STALLED": "REPLAN_OR_ASK_HUMAN",
                "REGRESSING": "STOP_AND_REASSESS",
            }[state],
        }
