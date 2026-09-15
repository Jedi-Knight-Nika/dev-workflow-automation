"""Validate work results independently from billing so malformed artifacts retain usage."""

from dataclasses import replace
from typing import Any

from pydantic import TypeAdapter

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.envelope import AgentEnvelope
from app.agent_runtime.domain.handoffs import validate_result


def decode_receipt(value: Any, work: AgentEnvelope | None) -> TurnReceipt:
    if work is None:
        return TypeAdapter(TurnReceipt).validate_python(value)
    if not isinstance(value, dict):
        raise TypeError("Receipt must be an object")
    receipt = TypeAdapter(TurnReceipt).validate_python({**value, "result": None})
    try:
        result = TypeAdapter(AgentEnvelope).validate_python(value.get("result"))
        validate_result(result, work)
        if result.payload["turn_id"] != receipt.native_turn_id:
            raise ValueError("Result receipt identity mismatch")
    except (ValueError, TypeError, KeyError):
        return replace(
            receipt,
            status="failed",
            failure_code="INVALID_AGENT_RESULT",
            raw_usage={**receipt.raw_usage, "rejected_agent_result": value.get("result")},
        )
    return replace(receipt, result=result)
