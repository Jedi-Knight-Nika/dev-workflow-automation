import asyncio
from datetime import UTC, datetime
from time import monotonic
from unittest.mock import AsyncMock

import anyio
import httpx
import pytest

from app.observability.observer.application import Observer
from app.observability.observer.domain import Evidence, LocalExplanation, Snapshot
from app.observability.observer.local_model import OllamaObserver


def companion(*, busy=False, memory_mb=8192):
    reads, store, model = AsyncMock(), AsyncMock(), AsyncMock()
    reads.snapshot.return_value = Snapshot(
        datetime.now(UTC).isoformat(),
        busy=busy,
        metrics_at=datetime.now(UTC).isoformat(),
        host={"host_memory_available": memory_mb * 1048576},
    )
    reads.execution_busy.return_value = busy
    reads.evidence.return_value = [
        Evidence("tasks:1", "One task is active.", "TASKS", None),
        Evidence("resources:missing", "Memory is unavailable.", "PROMETHEUS", None, False),
    ]
    store.question.return_value = {
        "result": None,
        "scope": {},
        "message": "Tell me about tasks",
        "conversation_id": "chat",
    }
    store.claim_question.return_value = True
    store.preference.return_value = {}
    store.history.return_value = []
    model.readiness.return_value = {"available": True, "memory_mb": 2048, "reason": None}
    model.explain.return_value = (
        LocalExplanation("One task is underway; its resource readings are missing.", ("tasks:1",)),
        {"status": "COMPLETED", "prompt_eval_count": 80, "eval_count": 25},
    )
    return (
        Observer(reads, store, model, local_enabled=True, reserve_mb=1024, thresholds={}),
        reads,
        store,
        model,
    )


async def test_local_chat_authors_an_answer_and_keeps_missing_source_notice():
    observer, _, store, model = companion()
    events = [event async for event in observer.answer("owner", "question")]
    result = events[-1]
    assert result["mode"] == "local"
    assert result["answer"].startswith("One task is underway")
    assert "PROMETHEUS is incomplete" in result["answer"]
    assert len(result["sources"]) == 2
    model.explain.assert_awaited_once()
    assert store.receipt.call_args.args[1]["prompt_eval_count"] == 80


@pytest.mark.parametrize("busy,memory_mb", [(True, 8192), (False, 2500)])
async def test_busy_engineering_or_insufficient_model_plus_reserve_never_invokes_ai(
    busy, memory_mb
):
    observer, _, _, model = companion(busy=busy, memory_mb=memory_mb)
    events = [event async for event in observer.answer("owner", "question")]
    assert events[-1]["mode"] == "deterministic"
    model.explain.assert_not_called()


async def test_new_engineering_work_cancels_only_the_local_explanation():
    observer, reads, _, model = companion()
    cancelled = asyncio.Event()

    async def long_call(*_):
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.set()

    model.explain.side_effect = long_call
    reads.execution_busy.side_effect = [False, True]
    answer, receipt = await observer._local_explanation("hello", [], [])
    assert answer is None
    assert receipt["reason"] == "ENGINEERING_PRIORITY"
    assert receipt["prompt_eval_count"] is None
    assert cancelled.is_set()


async def test_work_arriving_during_readiness_prevents_inference():
    observer, reads, _, model = companion()
    reads.execution_busy.return_value = True
    events = [event async for event in observer.answer("owner", "question")]
    assert events[-1]["mode"] == "deterministic"
    model.readiness.assert_awaited_once_with(fresh=True)
    model.explain.assert_not_called()


async def test_capacity_and_its_followup_cannot_be_overruled_by_model():
    observer, reads, store, model = companion()
    reads.snapshot.return_value.host["host_disk"] = 96.2
    store.question.return_value["message"] = "what"
    store.history.return_value = [
        {"role": "user", "content": "Can the host run another task?"},
        {"role": "assistant", "content": "Old reply"},
        {"role": "user", "content": "what"},
    ]
    result = [event async for event in observer.answer("owner", "question")][-1]
    assert "would not start another task" in result["answer"]
    assert "96.2%" in result["answer"]
    model.explain.assert_not_called()


async def test_release_only_unloads_our_owned_model():
    model = OllamaObserver("http://ollama:11434", "qwen3.5:2b")
    model.warm_until = monotonic() + 60
    model._json = AsyncMock(return_value={"models": [{"name": "qwen3:4b"}]})
    await model.release()
    model._json.assert_awaited_once_with("GET", "/api/ps")
    model.warm_until = monotonic() + 60
    model._json = AsyncMock(return_value={"models": [{"name": model.model}]})
    await model.release()
    assert model._json.call_args.args == (
        "POST",
        "/api/generate",
        {"model": model.model, "keep_alive": 0},
    )
    assert model.warm_until == 0


@pytest.mark.parametrize("inventory", [{}, {"models": None}, {"models": [None]}])
async def test_malformed_local_inventory_fails_closed(inventory):
    model = OllamaObserver("http://ollama:11434", "qwen3.5:2b")
    model._json = AsyncMock(return_value=inventory)
    assert (await model.models())["reachable"] is False


async def test_readiness_refresh_does_not_evict_new_interpreter_model():
    model = OllamaObserver("http://ollama:11434", "qwen3.5:2b")
    loaded = {"models": []}

    async def response(_method, path, *_):
        return {
            "/api/tags": {"models": [{"name": model.model, "size": 1000000000}]},
            "/api/show": {"capabilities": ["completion"]},
            "/api/ps": loaded,
        }[path]

    model._json = AsyncMock(side_effect=response)
    assert (await model.readiness())["available"]
    loaded["models"] = [{"name": "qwen3:4b"}]
    assert not (await model.readiness(fresh=True))["available"]


async def test_response_timeout_bounds_even_a_slow_trickle(monkeypatch):
    class Trickle(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.01)
                yield b" "

    client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=Trickle()))
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(**kwargs, transport=transport)
    )
    model = OllamaObserver("http://ollama:11434", "qwen3.5:2b", timeout=0.05)
    with pytest.raises(TimeoutError):
        await model._json("POST", "/api/chat")


async def test_stream_disconnect_preserves_bounded_cancellation_bookkeeping():
    observer, _, store, model = companion()
    running = asyncio.Event()
    recorded = []

    async def long_call(*_):
        running.set()
        await asyncio.sleep(60)

    async def receipt(_identifier, value):
        await asyncio.sleep(0)  # A database await must survive ASGI level cancellation.
        recorded.append(value["status"])

    async def consume():
        async for _ in observer.answer("owner", "question"):
            pass

    model.explain.side_effect = long_call
    store.receipt.side_effect = receipt
    async with anyio.create_task_group() as group:
        group.start_soon(consume)
        await running.wait()
        group.cancel_scope.cancel()
    assert recorded == ["STARTED", "INTERRUPTED"]
    store.finish_question.assert_awaited_once()


async def test_local_adapter_returns_natural_text_without_private_thinking():
    model = OllamaObserver("http://ollama:11434", "qwen3.5:2b", output_tokens=256)
    model._json = AsyncMock(
        return_value={
            "done": True,
            "message": {
                "content": '{"answer":"Hi! I can help you understand current tasks and costs.","fact_ids":["product:1"]}',
                "thinking": "private reasoning must not be persisted",
            },
            "prompt_eval_count": 100,
            "eval_count": 30,
        }
    )
    answer, receipt = await model.explain(
        "hello", [Evidence("product:1", "I explain tasks and costs.", "PRODUCT", None)], []
    )
    assert answer and answer.answer.startswith("Hi!")
    assert "private reasoning" not in str(answer) + str(receipt)
    assert model._json.call_args.args[2]["options"]["num_predict"] == 256
    assert "tools" not in model._json.call_args.args[2]


async def test_model_metadata_has_a_separate_bounded_limit(monkeypatch):
    client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"license": "x" * 72000}))
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(**kwargs, transport=transport)
    )
    model = OllamaObserver("http://ollama:11434", "qwen3.5:2b")
    assert len((await model._json("POST", "/api/show"))["license"]) == 72000
    with pytest.raises(ValueError, match="too large"):
        await model._json("POST", "/api/chat")


async def test_master_and_ai_policy_changes_apply_without_restart(monkeypatch):
    from app.bootstrap import observer as bootstrap

    observer, _, _, _ = companion()
    monkeypatch.setattr(bootstrap, "get_observer", lambda: observer)
    runtime = bootstrap.ObserverRuntime()
    settings = {
        "enabled": True,
        "local_ai_enabled": True,
        "model": "qwen3.5:2b",
        "memory_reserve_mb": 1024,
        "output_tokens": 256,
        "response_timeout_seconds": 30,
    }
    await runtime.apply(settings)
    assert observer.local_enabled and isinstance(observer.model, OllamaObserver)
    # Local AI off leaves the companion and engineering functions untouched.
    await runtime.apply({**settings, "local_ai_enabled": False})
    assert runtime.enabled and observer.model is None and not observer.local_enabled
    await runtime.apply(settings)
    assert observer.local_enabled and observer.model
    runtime.residency_guard.cancel()
    await asyncio.gather(runtime.residency_guard, return_exceptions=True)
