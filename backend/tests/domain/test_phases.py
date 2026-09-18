import pytest

from app.engineering.domain.lifecycle import (
    Action,
    EngineeringState,
    InvalidTransition,
    Stage,
    TaskStatus,
    transition,
)
from app.engineering.domain.phases import PHASE_ACTIONS, PHASE_RESULTS, PHASES


def test_only_active_phases_dispatch_and_only_merge_can_complete_delivery():
    assert set(PHASES) == set(Stage) - {Stage.REVIEWING, Stage.COMPLETE}
    assert PHASE_ACTIONS[Stage.DEVELOPING] == PHASE_ACTIONS[Stage.FIXING]
    assert [name for name, results in PHASE_RESULTS.items() if Action.MERGED in results] == [
        "MERGE_PR"
    ]
    assert set(PHASE_ACTIONS.values()) == set(PHASE_RESULTS)


@pytest.mark.parametrize(
    "stage,result",
    [(stage, result) for stage, phase in PHASES.items() for result in phase.results],
)
def test_phase_outcomes_are_accepted_by_lifecycle(stage, result):
    state = EngineeringState(status=TaskStatus.ACTIVE, stage=stage)
    if stage == Stage.FIXING and result == Action.BOUNDED_REPAIR:
        with pytest.raises(InvalidTransition):
            transition(state, result)
        return
    transition(state, result)
