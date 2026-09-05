from app.domain.agents import AgentRole
from app.domain.jobs import JobExecutionState


def test_worker_execution_types_are_transport_neutral_strings() -> None:
    assert [role.value for role in AgentRole] == [
        "INTAKE",
        "THINKER",
        "EXECUTOR",
        "REVIEWER",
        "TESTER",
    ]
    assert [state.value for state in JobExecutionState] == [
        "SUCCEEDED",
        "FAILED",
        "TIMED_OUT",
    ]
