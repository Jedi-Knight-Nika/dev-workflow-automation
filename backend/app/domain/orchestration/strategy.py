from dataclasses import asdict, dataclass
from enum import StrEnum


class ProfileLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskLevel(StrEnum):
    LOW = "LOW"
    ELEVATED = "ELEVATED"
    CRITICAL = "CRITICAL"


class StrategyKind(StrEnum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    HIGH_ASSURANCE = "HIGH_ASSURANCE"
    PARALLEL_INVESTIGATION = "PARALLEL_INVESTIGATION"


@dataclass(frozen=True, slots=True)
class TaskProfile:
    complexity: ProfileLevel
    risk: RiskLevel
    parallelizability: ProfileLevel
    uncertainty: ProfileLevel
    tool_density: ProfileLevel
    reasons: tuple[str, ...]
    version: str = "v1"

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


@dataclass(frozen=True, slots=True)
class ExecutionStrategy:
    kind: StrategyKind
    max_job_turns: int
    max_tool_calls: int
    max_replans: int
    max_test_cycles: int
    max_review_cycles: int
    require_human_gate: bool
    allow_parallel_specialists: bool = False
    max_parallel_specialists: int = 0
    version: str = "v1"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class TaskProfiler:
    """Small explainable classifier. It may be rerun when better evidence becomes available."""

    _critical = frozenset({"production", "credential", "secret", "payment", "permission"})
    _elevated = frozenset({"authentication", "authorization", "security", "migration", "schema"})
    _uncertain = frozenset({"investigate", "unknown", "clarify", "research", "unsure"})
    _broad = frozenset({"cross-service", "multiple services", "architecture", "redesign"})

    def profile(self, *, title: str, description: str, labels: list[str]) -> TaskProfile:
        text = " ".join([title, description, *labels]).casefold()
        reasons: list[str] = []
        risk = RiskLevel.LOW
        if any(signal in text for signal in self._critical):
            risk = RiskLevel.CRITICAL
            reasons.append("critical-impact domain signal")
        elif any(signal in text for signal in self._elevated):
            risk = RiskLevel.ELEVATED
            reasons.append("elevated-risk domain signal")
        uncertainty = (
            ProfileLevel.HIGH
            if any(signal in text for signal in self._uncertain)
            else ProfileLevel.LOW
        )
        if uncertainty == ProfileLevel.HIGH:
            reasons.append("requirements or investigation signal")
        complexity = ProfileLevel.LOW
        if any(signal in text for signal in self._broad) or len(description) > 1500:
            complexity = ProfileLevel.HIGH
            reasons.append("broad change surface")
        elif len(description) > 400 or risk != RiskLevel.LOW:
            complexity = ProfileLevel.MEDIUM
            reasons.append("non-trivial task detail or risk")
        parallel = (
            ProfileLevel.HIGH
            if any(signal in text for signal in ("independent", "parallel", "multiple services"))
            else ProfileLevel.LOW
        )
        tool_density = (
            ProfileLevel.HIGH
            if sum(signal in text for signal in ("github", "linear", "database", "api", "deploy"))
            >= 3
            else ProfileLevel.MEDIUM
            if sum(signal in text for signal in ("github", "linear", "database", "api")) >= 2
            else ProfileLevel.LOW
        )
        return TaskProfile(
            complexity,
            risk,
            parallel,
            uncertainty,
            tool_density,
            tuple(reasons or ["bounded task"]),
        )


def resolve_execution_strategy(profile: TaskProfile) -> ExecutionStrategy:
    if profile.risk == RiskLevel.CRITICAL:
        return ExecutionStrategy(StrategyKind.HIGH_ASSURANCE, 24, 80, 2, 3, 3, True)
    if profile.complexity == ProfileLevel.HIGH and profile.parallelizability == ProfileLevel.HIGH:
        return ExecutionStrategy(
            StrategyKind.PARALLEL_INVESTIGATION, 24, 80, 3, 3, 3, False, True, 3
        )
    if profile.complexity == ProfileLevel.HIGH or profile.risk == RiskLevel.ELEVATED:
        return ExecutionStrategy(StrategyKind.HIGH_ASSURANCE, 24, 70, 3, 3, 3, False)
    if profile.complexity == ProfileLevel.LOW and profile.uncertainty == ProfileLevel.LOW:
        return ExecutionStrategy(StrategyKind.FAST, 10, 30, 1, 2, 2, False)
    return ExecutionStrategy(StrategyKind.STANDARD, 16, 50, 2, 3, 3, False)
