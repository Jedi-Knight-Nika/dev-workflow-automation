"""Reproducible protocol/model experiment. Offline by default; never changes tasks.

Run from backend: .venv/bin/python -m evaluations.benchmark_coordinator --output /tmp/codec.jsonl
Live runs require --live --max-cost-usd and an explicit verified --pricing JSON file.
"""

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from time import monotonic
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx

from app.agent_runtime.domain.envelope import AgentEnvelope
from app.agent_runtime.domain.usage import Pricing, Usage
from app.agent_runtime.infrastructure.agent_codec import canonical, decode, encode
from app.coordinator.infrastructure.model import CONTRACT
from app.coordinator.infrastructure.schemas import DecisionSchema, parse_decision
from app.intake.infrastructure.cloud_wire import normalized_usage, request_body, response_text

MODELS = [
    "openai/gpt-5.6-luna",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-sol",
    "deepseek/deepseek-flash",
]
CODECS: list[Literal["JSON_VERBOSE", "JSON_COMPACT", "DSL_V1", "COMPRESSED_V1"]] = [
    "JSON_VERBOSE",
    "JSON_COMPACT",
    "DSL_V1",
    "COMPRESSED_V1",
]
DICTIONARY = "AE1 is a lossless packet: v=version,t=type,id=task_id,r=requirement_revision,sha=current_sha,p=payload,e=evidence_refs. Each DSL line is key=JSON-value. Read the task situation in p. AEZ1 contains dictionary and packet: recursively replace object keys ~N with dictionary[N], and ~~ with a literal ~ prefix. Values remain verbatim JSON."


async def run(args: argparse.Namespace) -> None:
    cases = [json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    if len(cases) > 100:
        raise ValueError("At most 100 evaluation cases")
    prices = json.loads(args.pricing.read_text()) if args.pricing else {}
    ceiling = Decimal(args.max_cost_usd) if args.max_cost_usd else Decimal(0)
    if args.live and (not ceiling.is_finite() or not 0 < ceiling <= 10 or not prices):
        raise ValueError("Live evaluation needs verified prices and a positive ceiling <= $10")
    spent = Decimal(0)
    # Exclusive output prevents an interrupted purchase from being silently replayed.
    with args.output.open("x") as output:

        def record(row: dict[str, Any]) -> None:
            output.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            output.flush()
            os.fsync(output.fileno())

        async with httpx.AsyncClient(timeout=45, trust_env=False) as client:
            for case in cases:
                historical = "situation" in case
                if (
                    historical
                    and args.live
                    and (case.get("label_source") != "HUMAN" or not case.get("expected_actions"))
                ):
                    raise ValueError(
                        "Historical live comparisons require human-labeled expected_actions"
                    )
                situation = case.get("situation") or {
                    "original_requirement": "Add a movable, resizable execution window while retaining read-only behavior.",
                    "status": case.get("status"),
                    "stage": "REVIEWING",
                    "trigger_provider": case.get("provider"),
                    "human_request": case.get("human_request"),
                    "events": [{"provider": case.get("provider"), "body": case.get("body")}],
                    "validation": [{"status": "PASSED", "sha": "a" * 40}],
                }
                packet = AgentEnvelope(
                    1,
                    "work",
                    UUID(case["task_id"]) if historical else uuid5(NAMESPACE_URL, case["id"]),
                    situation.get("requirement_revision", 1),
                    situation.get("current_sha"),
                    {"request": situation["original_requirement"], **situation},
                )
                for codec in CODECS:
                    wire = encode(packet, codec)
                    assert decode(wire, codec) == packet
                    base = {
                        "case_id": case["id"],
                        "codec": codec,
                        "source": case.get("source", "synthetic_fixture"),
                        "canonical": canonical(packet),
                        "wire_sha256": hashlib.sha256(wire.encode()).hexdigest(),
                        "wire_bytes": len(wire.encode()),
                        "codec_roundtrip": True,
                    }
                    if not args.live:
                        record(
                            {
                                **base,
                                "mode": "offline",
                                "actual_input_tokens": None,
                                "semantic_accuracy": None,
                                "patch_acceptance": None,
                            }
                        )
                        continue
                    for configured in args.models:
                        provider, model = configured.split("/", 1)
                        if provider not in {"openai", "deepseek"}:
                            raise ValueError("Unsupported benchmark provider")
                        price = prices[configured]
                        if not str(price.get("source_url", "")).startswith("https://"):
                            raise ValueError("Verified prices need their source URL")
                        pricing = Pricing(
                            Decimal(str(price["input_per_million"])),
                            Decimal(str(price["output_per_million"])),
                            Decimal(str(price["cached_input_per_million"]))
                            if price.get("cached_input_per_million") is not None
                            else None,
                            Decimal(str(price["cache_write_per_million"]))
                            if price.get("cache_write_per_million") is not None
                            else None,
                        )
                        url, payload = request_body(
                            provider,
                            model,
                            [
                                {
                                    "role": "system",
                                    "content": CONTRACT
                                    + "\n"
                                    + DICTIONARY
                                    + "\nSchema: "
                                    + json.dumps(DecisionSchema.model_json_schema()),
                                },
                                {"role": "user", "content": wire},
                            ],
                        )
                        payload["max_output_tokens" if provider == "openai" else "max_tokens"] = (
                            1600
                        )
                        reserve = pricing.calculate(
                            Usage(len(json.dumps(payload).encode()) + 2048, 1600, 0, 0)
                        )
                        if reserve is None or spent + reserve > ceiling:
                            record({**base, "model": configured, "status": "BUDGET_NOT_ADMITTED"})
                            return
                        key = os.environ[
                            "OPENAI_API_KEY" if provider == "openai" else "DEEPSEEK_API_KEY"
                        ]
                        record(
                            {
                                **base,
                                "model": configured,
                                "status": "ADMITTED",
                                "reserved_usd": reserve,
                            }
                        )
                        started = monotonic()
                        try:
                            response = await client.post(
                                url, headers={"Authorization": f"Bearer {key}"}, json=payload
                            )
                            response.raise_for_status()
                            if len(response.content) > 100000:
                                raise ValueError("Oversized benchmark response")
                            data = response.json()
                            usage = normalized_usage(provider, data.get("usage") or {})
                            amount = pricing.calculate(usage)
                            if amount is None:
                                raise ValueError("Unknown usage; reconcile before a new experiment")
                            spent += amount
                            try:
                                decision = parse_decision(json.loads(response_text(provider, data)))
                                complete = (
                                    data.get("status") == "completed"
                                    if provider == "openai"
                                    else (data.get("choices") or [{}])[0].get("finish_reason")
                                    == "stop"
                                )
                                valid, accurate = (
                                    complete,
                                    complete and decision.action in case["expected_actions"],
                                )
                            except ValueError:
                                valid, accurate = False, False
                            record(
                                {
                                    **base,
                                    "model": configured,
                                    "status": "COMPLETED",
                                    "schema_valid": valid,
                                    "semantic_accuracy": accurate,
                                    "actual_input_tokens": usage.input_tokens,
                                    "usage": asdict(usage),
                                    "cost_usd": amount,
                                    "latency_seconds": monotonic() - started,
                                    "patch_acceptance": None,
                                }
                            )
                            if spent > ceiling:
                                return
                        except Exception as exc:
                            record(
                                {
                                    **base,
                                    "model": configured,
                                    "status": "UNKNOWN",
                                    "error_type": type(exc).__name__,
                                }
                            )
                            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("evaluations/coordinator_cases.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-cost-usd")
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--models", nargs="+", default=MODELS)
    asyncio.run(run(parser.parse_args()))
