"""Use cases depend only on Observer contracts. Engineering commands cannot be injected."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from anyio import move_on_after

from app.observability.observer.domain import (
    Evidence,
    LocalExplanation,
    Scope,
    Snapshot,
    capacity_advice,
    capacity_question,
    capacity_reason,
    choose_tools,
    detect,
    question_subject,
)
from app.observability.observer.ports import LocalObserverModel, ObserverReads, ObserverStore


class Observer:
    def __init__(
        self,
        reads: ObserverReads,
        store: ObserverStore,
        model: LocalObserverModel | None,
        *,
        local_enabled: bool,
        reserve_mb: int,
        thresholds: dict[str, int],
        record: Callable[[str, float], None] = lambda _name, _value: None,
    ) -> None:
        self.reads, self.store, self.model = reads, store, model
        self.local_enabled, self.reserve_mb, self.thresholds = local_enabled, reserve_mb, thresholds
        self.record = record
        self.installing = False

    async def local_reason(self, snapshot: Snapshot, *, fresh: bool = False) -> str | None:
        if self.installing:
            return "Local model setup is running; chat will use deterministic facts."
        reason = capacity_reason(snapshot, self.local_enabled, self.reserve_mb)
        if reason or self.model is None:
            return reason or "Local AI is disabled."
        readiness = await self.model.readiness(fresh=fresh)
        if not readiness["available"]:
            return str(readiness["reason"])
        # Leave the configured reserve AFTER estimated weights + KV/runtime use.
        return capacity_reason(snapshot, True, self.reserve_mb + int(readiness["memory_mb"]))

    async def detect_attention(self) -> None:
        started = perf_counter()
        snapshot = await self.reads.snapshot(Scope(), fresh=True)
        sources = {"TASKS", "AI_RUNS", "INCIDENTS", "PROMETHEUS"} - set(snapshot.partial_sources)
        if snapshot.tasks_truncated:
            sources -= {"TASKS", "AI_RUNS"}  # Absence from a bounded page is not recovery.
        await self.store.synchronize(
            detect(snapshot, self.thresholds), sources, snapshot.measured_at
        )
        self.record("anomaly_detection_duration_seconds", perf_counter() - started)

    async def status(self, scope: Scope) -> dict[str, Any]:
        snapshot = await self.reads.snapshot(scope)
        events = await self.store.events(scope)
        visible = [e for e in events if e["status"] == "OPEN"]
        severity = (
            "CRITICAL"
            if any(e["severity"] == "CRITICAL" for e in events)
            else "WARNING"
            if any(e["severity"] == "WARNING" for e in visible)
            else "NONE"
        )
        reason = await self.local_reason(snapshot)
        ready = reason is None
        return {
            "enabled": True,
            "ai_available": ready,
            "mode": "IDLE" if ready else "SLEEPING",
            "highest_severity": severity,
            "open_attention_count": len(visible),
            "partial_sources": snapshot.partial_sources,
            "sampled_at": snapshot.measured_at,
            "reason": reason,
            "events": events,
            "read_only": True,
            "paid_cloud_enabled": False,
        }

    async def briefing(self, scope: Scope, owner: str) -> dict[str, Any]:
        self.record("briefings_total", 1)
        state = await self.status(scope)
        preferences = await self.store.preference(owner)
        active = [e for e in state["events"] if e["status"] == "OPEN"]
        active.sort(key=lambda e: e["severity"] != "CRITICAL")
        facts: list[Evidence] = []
        if active:
            facts = [
                Evidence(e["id"], e["title"] + ".", e["source"], e["last_seen_at"])
                for e in active[:3]
            ]
        else:
            facts = (await self.reads.evidence("tasks", scope, 1, None))[:1]
        if state["partial_sources"]:
            facts.append(
                Evidence(
                    "partial",
                    "Some sources are unavailable: "
                    + ", ".join(state["partial_sources"])
                    + ". Missing monitoring does not establish an outage.",
                    "SOURCE_HEALTH",
                    state["sampled_at"],
                    False,
                )
            )
        changes = await self.reads.evidence("changes", scope, 1, preferences.get("last_seen_at"))
        return {
            **state,
            "message": " ".join(f.text for f in facts),
            "sources": [asdict(f) for f in facts],
            "changes": [asdict(f) for f in changes],
            "preferences": preferences,
            "suggested_questions": [
                "What needs attention?",
                "What changed since my visit?",
                "Why is this task expensive?" if scope.task_id else "Which agents cost the most?",
                "Can the host run another task?",
            ],
        }

    async def answer(self, owner: str, identifier: str) -> AsyncIterator[dict[str, Any]]:
        started = perf_counter()
        request = await self.store.question(owner, identifier)
        if request is None:
            yield {"type": "observer.failed", "message": "Question not found."}
            return
        if request["result"]:
            yield {"type": "observer.completed", **request["result"]}
            return
        if not await self.store.claim_question(owner, identifier):
            yield {
                "type": "observer.failed",
                "message": "The assistant is busy or this question was interrupted. Open history or ask again.",
            }
            return
        yield {"type": "observer.started"}
        self.record("questions_total", 1)
        evidence: list[Evidence] = []
        mode, reason = "deterministic", None
        explanation: LocalExplanation | None = None
        tools: list[str] = []
        local_started = False
        try:
            async with asyncio.timeout(85):
                scope = Scope(**request["scope"])
                prefs = await self.store.preference(owner)
                message = request["message"]
                history = await self.store.history(owner, request["conversation_id"])
                subject = question_subject(message, history)
                days = 7 if "week" in message.lower() or "7 day" in message.lower() else 30
                tools = (
                    ["resources"] if capacity_question(subject) else choose_tools(subject, scope)
                )
                for tool in tools:
                    self.record("tool_calls_total", 1)
                    yield {"type": "observer.tool_started", "tool": tool}
                    try:
                        async with asyncio.timeout(8):
                            if tool == "attention":
                                rows = await self.store.events(scope)
                                found = [
                                    Evidence(
                                        e["id"], e["title"] + ".", e["source"], e["last_seen_at"]
                                    )
                                    for e in rows
                                    if e["status"] == "OPEN"
                                ][:6]
                                if not found:
                                    found = [
                                        Evidence(
                                            "attention:none",
                                            "No open attention events are recorded. This is not a guarantee that every source is healthy.",
                                            "ATTENTION",
                                            datetime.now(UTC).isoformat(),
                                        )
                                    ]
                            else:
                                found = await self.reads.evidence(
                                    tool, scope, days, prefs.get("last_seen_at")
                                )
                                if tool == "product":
                                    found = found[:2]
                            evidence.extend(found)
                    except Exception:  # noqa: BLE001 -- optional read-port failure becomes partial evidence
                        self.record("tool_failures_total", 1)
                        evidence.append(
                            Evidence(
                                tool + ":unavailable",
                                f"{tool.replace('_', ' ').capitalize()} data is currently unavailable.",
                                tool.upper(),
                                None,
                                False,
                            )
                        )
                    yield {"type": "observer.tool_finished", "tool": tool}
                # Hard bound applied before model admission and persistence.
                evidence = [
                    Evidence(e.key, e.text[:420], e.source, e.measured_at, e.complete)
                    for e in evidence[:12]
                ]
                snapshot = await self.reads.snapshot(scope, fresh=True)
                if capacity_question(subject):
                    evidence = [
                        Evidence(
                            "capacity:assessment",
                            capacity_advice(snapshot),
                            "CAPACITY_POLICY",
                            snapshot.metrics_at,
                        )
                    ]
                    reason = "Capacity advice is calculated without a model."
                else:
                    reason = await self.local_reason(snapshot, fresh=True)
                if reason and self.local_enabled and not capacity_question(subject):
                    self.record("capacity_denied_total", 1)
                if reason is None and self.model:
                    await self.store.receipt(
                        identifier,
                        {"status": "STARTED", "prompt_eval_count": None, "eval_count": None},
                    )
                    local_started = True
                    self.record("model_requests_total", 1)
                    yield {
                        "type": "observer.model_started",
                        "message": "Local AI is composing an answer from verified sources.",
                    }
                    explanation, receipt = await self._local_explanation(message, evidence, history)
                    await self.store.receipt(identifier, receipt)
                    local_started = False
                    if receipt.get("prompt_eval_count") is not None:
                        self.record("model_prompt_tokens_total", receipt["prompt_eval_count"])
                    if receipt.get("eval_count") is not None:
                        self.record("model_output_tokens_total", receipt["eval_count"])
                    if explanation:
                        ordered = {e.key: e for e in evidence}
                        evidence = [ordered[k] for k in explanation.fact_ids] + [
                            e
                            for e in evidence
                            if not e.complete and e.key not in explanation.fact_ids
                        ][:4]
                        mode = "local"
                    else:
                        self.record("model_failures_total", 1)
                        reason = (
                            "Engineering work took priority; showing verified facts."
                            if receipt.get("reason") == "ENGINEERING_PRIORITY"
                            else "Local explanation reached its limit or was unavailable; showing verified facts."
                        )
                elif reason is None:
                    reason = "Local model not provisioned; showing verified facts."
        except asyncio.CancelledError:
            # A page disconnect cancels the upstream call; hiding the panel does not.
            # ASGI disconnects use level cancellation. Shield only bounded
            # bookkeeping so the Observer pool can return its connection.
            with move_on_after(3, shield=True):
                if local_started:
                    await self.store.receipt(
                        identifier,
                        {"status": "INTERRUPTED", "prompt_eval_count": None, "eval_count": None},
                    )
                await self.store.finish_question(
                    owner,
                    identifier,
                    {
                        "answer": "Question interrupted. No engineering action was taken.",
                        "sources": [],
                        "mode": "deterministic",
                        "tools": tools,
                    },
                )
            raise
        except Exception:  # noqa: BLE001 -- companion failure cannot escape into execution
            explanation = None
            if local_started:
                await self.store.receipt(
                    identifier,
                    {"status": "INTERRUPTED", "prompt_eval_count": None, "eval_count": None},
                )
            reason = "The assistant reached its time or availability limit. No engineering action was taken."
        facts = evidence[:8]
        incomplete = [e for e in evidence[8:] if not e.complete][:4]
        facts.extend(incomplete)
        answer = (
            "\n\n".join(f.text for f in facts)
            or "I cannot retrieve the necessary facts right now. Engineering execution is independent of this assistant."
        )
        if explanation:
            answer = explanation.answer
            # A model cannot suppress missing-data notices from the evidence layer.
            missing = list(dict.fromkeys(e.source for e in facts if not e.complete))
            if missing:
                answer += (
                    "\n\nData limitation: " + ", ".join(missing) + " is incomplete or unavailable."
                )
        result = {
            "answer": answer,
            "sources": [asdict(f) for f in facts],
            "mode": mode,
            "reason": reason,
            "tools": tools,
            "freshness": datetime.now(UTC).isoformat(),
        }
        if mode == "deterministic":
            self.record("deterministic_fallback_total", 1)
        self.record("question_duration_seconds", perf_counter() - started)
        await self.store.finish_question(owner, identifier, result)
        # Only validated public text is streamed, never private model thinking.
        for start in range(0, len(answer), 120):
            yield {"type": "observer.text_delta", "text": answer[start : start + 120]}
        yield {"type": "observer.completed", **result}

    async def _local_explanation(
        self, message: str, evidence: list[Evidence], history: list[dict[str, Any]]
    ) -> tuple[LocalExplanation | None, dict[str, Any]]:
        assert self.model is not None
        if not self.local_enabled or self.installing or await self.reads.execution_busy():
            return None, {
                "status": "SKIPPED",
                "reason": "ENGINEERING_PRIORITY",
                "prompt_eval_count": 0,
                "eval_count": 0,
            }
        task = asyncio.create_task(self.model.explain(message, evidence, history))
        try:
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=2)
                if done:
                    break
                # Yield to new actionable work arriving after admission, too.
                if not self.local_enabled or self.installing or await self.reads.execution_busy():
                    return None, {
                        "status": "INTERRUPTED",
                        "reason": "ENGINEERING_PRIORITY",
                        "prompt_eval_count": None,
                        "eval_count": None,
                    }
            return await task
        finally:
            if not task.done():
                task.cancel()
                with move_on_after(3, shield=True):
                    await asyncio.gather(task, return_exceptions=True)
