import pytest

from app.agent_runtime.infrastructure.models import AIRun
from app.agent_runtime.infrastructure.patch_recovery import unspent_failure


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"input_tokens": 1},
        {"usage_complete": False},
        {"calculated_cost_usd": None},
        {"status": "RUNNING"},
        {"token_efficiency": {"inference_cycle_count": 1}},
    ],
)
def test_only_proven_zero_call_failure_can_resume(change):
    values = {
        "harness": "patch",
        "status": "FAILED",
        "failure_code": "PATCH_FAILED",
        "usage_complete": True,
        "input_tokens": 0,
        "output_tokens": 0,
        "calculated_cost_usd": 0,
        "token_efficiency": {"inference_cycle_count": 0},
    }
    assert unspent_failure(AIRun(**(values | change))) is (not change)
