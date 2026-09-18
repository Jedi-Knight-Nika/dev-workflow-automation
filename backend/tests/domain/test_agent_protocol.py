from uuid import uuid4

import pytest

from app.agent_runtime.domain.envelope import AgentEnvelope
from app.agent_runtime.domain.progress import ProgressWindow
from app.agent_runtime.infrastructure.agent_codec import decode, encode


@pytest.mark.parametrize("codec", ["JSON_VERBOSE", "JSON_COMPACT", "DSL_V1", "COMPRESSED_V1"])
def test_codec_roundtrip_preserves_human_prose_and_errors(codec):
    packet = AgentEnvelope(
        1,
        "repair",
        uuid4(),
        2,
        "a" * 40,
        {"request": 'Keep this exact: \n|e=unknown = "ა"', "error": "line 88: foo != bar\n  ^"},
    )
    assert decode(encode(packet, codec), codec) == packet


@pytest.mark.parametrize(
    "encoded,codec",
    [
        ("{}", "JSON_VERBOSE"),
        ('{"v":1,"v":2}', "JSON_COMPACT"),
        ("AE2\np={}", "DSL_V1"),
        ("AE1\nv=1\nv=2", "DSL_V1"),
    ],
)
def test_malformed_or_duplicate_protocol_fields_are_rejected(encoded, codec):
    with pytest.raises(ValueError):
        decode(encoded, codec)


@pytest.mark.parametrize(
    "evidence,expected",
    [
        ({"checks_improved": True}, "PRODUCTIVE"),
        ({"diff_changed": True}, "MARGINAL"),
        ({"repeated_failures": 2}, "STALLED"),
        ({"checks_regressed": True}, "REGRESSING"),
    ],
)
def test_progress_is_based_on_explicit_evidence(evidence, expected):
    assert ProgressWindow(100, 70, **evidence).classify() == expected
