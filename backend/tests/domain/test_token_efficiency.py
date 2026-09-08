from dataclasses import replace

import pytest

from app.agent_runtime.application.developer_progress_governor import DeveloperProgressGovernor
from app.agent_runtime.domain.token_efficiency_policy import TokenEfficiencyPolicy


def test_profiles_are_bounded_and_instrumentation_never_stops_paid_work():
    for name, ceiling in [("FAST", 100000), ("STANDARD", 170000), ("LARGE", 220000)]:
        policy = TokenEfficiencyPolicy.parse({"execution_profile": name})
        assert policy.active_context_hard_tokens == ceiling
        governor = DeveloperProgressGovernor(policy)
        assert governor.observe(900000, 900000) == ([], None)
    with pytest.raises(ValueError):
        TokenEfficiencyPolicy.parse({"active_context_soft_tokens": 200000})
    with pytest.raises(ValueError):
        TokenEfficiencyPolicy.parse({"max_model_visible_tool_result_tokens": 10001})


def test_warnings_are_once_and_hard_stop_needs_real_lack_of_progress():
    policy = replace(TokenEfficiencyPolicy(), mode="ENFORCE")
    governor = DeveloperProgressGovernor(policy)
    warnings, stop = governor.observe(41000, 60000)
    assert "EXPLORATION_WARNING" in warnings and stop is None
    assert governor.observe(41000, 60000) == ([], None)
    governor.progress("changed-source")
    assert governor.observe(72000, 60000)[1] is None
    governor.progress("changed-source")  # Same diff is not progress.
    assert governor.observe(112000, 60000)[1] == "NO_PROGRESS"
    assert governor.first_edit == 41000


def test_counter_survives_native_rollover_and_polling_is_not_a_loop():
    governor = DeveloperProgressGovernor(replace(TokenEfficiencyPolicy(), mode="ENFORCE"))
    governor.restore(
        {
            "input_tokens_observed": 50000,
            "tokens_to_first_edit": 12000,
            "tokens_since_last_progress": 1000,
            "diff_fingerprint": "abc",
        }
    )
    for _ in range(10):
        governor.command("poll", failed=True, expensive=False)
    assert governor.observe(51000, 10000)[1] is None
    for _ in range(4):
        governor.command("unchanged-test", failed=True, expensive=True)
    assert governor.observe(52000, 11000)[1] == "REPEATED_TOOL_LOOP"
    assert governor.snapshot()["tokens_to_first_edit"] == 12000


def test_cycle_and_cached_input_telemetry_is_cumulative():
    governor = DeveloperProgressGovernor(TokenEfficiencyPolicy())
    governor.observe(1000, 900, 700)
    governor.observe(1800, 1200, 500)
    snapshot = governor.snapshot()
    assert snapshot["inference_cycle_count"] == 2
    assert snapshot["cached_input_tokens_observed"] == 1200
    assert snapshot["uncached_input_tokens_observed"] == 600
