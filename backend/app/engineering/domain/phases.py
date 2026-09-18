from dataclasses import dataclass
from types import MappingProxyType

from app.engineering.domain.lifecycle import Action, Stage


@dataclass(frozen=True)
class Phase:
    action: str
    results: frozenset[Action]


DEVELOPMENT = Phase(
    "DEVELOPER_TURN",
    frozenset(
        {Action.IMPLEMENTED, Action.NEEDS_PLAN, Action.BOUNDED_REPAIR, Action.VALIDATE_CANDIDATE}
    ),
)
PHASES = MappingProxyType(
    {
        Stage.INTAKE: Phase("INTERPRET_EVENT", frozenset({Action.START})),
        Stage.PLANNING: Phase("THINKER_TURN", frozenset({Action.PLAN_READY})),
        Stage.DEVELOPING: DEVELOPMENT,
        Stage.FIXING: DEVELOPMENT,
        Stage.VALIDATING: Phase(
            "RUN_VALIDATION", frozenset({Action.VALIDATION_PASSED, Action.VALIDATION_FAILED})
        ),
        Stage.PUBLISHING: Phase("PUBLISH_PR", frozenset({Action.PUBLISHED})),
        Stage.MERGING: Phase("MERGE_PR", frozenset({Action.MERGED, Action.MERGE_RECHECK})),
    }
)
PHASE_ACTIONS = MappingProxyType({stage: phase.action for stage, phase in PHASES.items()})
PHASE_RESULTS = MappingProxyType({phase.action: phase.results for phase in PHASES.values()})
