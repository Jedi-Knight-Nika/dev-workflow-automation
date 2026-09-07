from app.domain.agents import AgentRole
from app.domain.jobs import JobExecutionState


def test_worker_execution_types_are_transport_neutral_strings() -> None:
    assert [role.value for role in AgentRole] == [
        "ORCHESTRATOR",
        "INTAKE",  # Historical rows remain readable; not an executable workflow role.
        "THINKER",
        "EXECUTOR",
        "REVIEWER",
        "TESTER",
        "DELIVERER",
    ]
    assert [state.value for state in JobExecutionState] == [
        "SUCCEEDED",
        "FAILED",
        "TIMED_OUT",
    ]
