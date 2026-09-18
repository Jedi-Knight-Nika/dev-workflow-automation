"""Lossless experimental wire codecs. Canonical state is always retained separately."""

import json
from typing import Any, Literal
from uuid import UUID

from app.agent_runtime.domain.envelope import AgentEnvelope, canonical
from app.agent_runtime.infrastructure.structural_compression import compress, decompress

Codec = Literal["JSON_VERBOSE", "JSON_COMPACT", "DSL_V1", "COMPRESSED_V1"]
KEYS = {
    "version": "v",
    "type": "t",
    "task_id": "id",
    "requirement_revision": "r",
    "current_sha": "sha",
    "payload": "p",
    "evidence_refs": "e",
}


def encode(packet: AgentEnvelope, codec: Codec) -> str:
    data = canonical(packet)
    if codec == "JSON_VERBOSE":
        return json.dumps(data, ensure_ascii=False, indent=2)
    compact = {KEYS[key]: value for key, value in data.items()}
    if codec == "COMPRESSED_V1":
        return "AEZ1\n" + json.dumps(compress(compact), ensure_ascii=False, separators=(",", ":"))
    if codec == "JSON_COMPACT":
        return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    if codec == "DSL_V1":
        # JSON-escaped values protect separators/newlines in verbatim human text.
        return "AE1\n" + "\n".join(
            key + "=" + json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            for key, value in compact.items()
        )
    raise ValueError("Unknown agent codec")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate packet field")
        result[key] = value
    return result


def decode(value: str, codec: Codec) -> AgentEnvelope:
    if len(value.encode()) > 100000:
        raise ValueError("Agent packet exceeds its size bound")
    if codec == "COMPRESSED_V1":
        if not value.startswith("AEZ1\n"):
            raise ValueError("Unsupported compression version")
        data = decompress(json.loads(value[5:], object_pairs_hook=_unique))
    elif codec == "DSL_V1":
        if not value.startswith("AE1\n"):
            raise ValueError("Unsupported DSL version")
        pairs = []
        for line in value.splitlines()[1:]:
            key, separator, encoded = line.partition("=")
            if not separator:
                raise ValueError("Invalid DSL field")
            pairs.append((key, json.loads(encoded, object_pairs_hook=_unique)))
        data = _unique(pairs)
    elif codec in {"JSON_VERBOSE", "JSON_COMPACT"}:
        data = json.loads(value, object_pairs_hook=_unique)
    else:
        raise ValueError("Unknown agent codec")
    if not isinstance(data, dict):
        raise TypeError("Agent packet must be an object")
    if codec != "JSON_VERBOSE":
        reverse = {v: k for k, v in KEYS.items()}
        if set(data) != set(reverse):
            raise ValueError("Agent packet fields do not match its version")
        data = {reverse[key]: value for key, value in data.items()}
    if set(data) != set(KEYS):
        raise ValueError("Agent packet fields do not match its version")
    if (
        type(data["version"]) is not int
        or type(data["requirement_revision"]) is not int
        or not isinstance(data["payload"], dict)
        or not isinstance(data["evidence_refs"], list)
        or any(not isinstance(e, str) for e in data["evidence_refs"])
    ):
        raise ValueError("Invalid agent packet types")
    data["task_id"] = UUID(data["task_id"])
    data["evidence_refs"] = tuple(data["evidence_refs"])
    return AgentEnvelope(**data)
