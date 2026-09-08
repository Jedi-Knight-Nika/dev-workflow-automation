import pytest
from pydantic import ValidationError

from app.interfaces.http.schemas.tasks import TaskCreate


def test_task_priority_is_bounded():
    with pytest.raises(ValidationError):
        TaskCreate(title="Task", priority=6)


@pytest.mark.parametrize("value", [None, 0, 0.5, 1, 7.25])
def test_estimates_are_nullable_relative_numbers(value):
    assert TaskCreate(title="Task", estimate=value).estimate == value


def test_estimate_is_not_negative():
    with pytest.raises(ValidationError):
        TaskCreate(title="Task", estimate=-1)
