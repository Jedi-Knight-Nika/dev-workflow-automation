import asyncio
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.agent_runtime.application.harness import TurnReceipt
from app.agent_runtime.domain.usage import Usage
from app.agent_runtime.infrastructure.container import RunnerMounts
from app.agent_runtime.infrastructure.docker_harness import (
    DockerFrames,
    DockerHarness,
    RunnerProtocolError,
    atomic_json,
)
from app.agent_runtime.infrastructure.runner import Manifest, await_controller
from app.agent_runtime.infrastructure.workspace_lock import workspace_lock


def frame(payload: bytes, stream: int = 1) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


def test_surviving_runner_prevents_a_second_writer_even_with_new_lease(tmp_path: Path) -> None:
    lock = tmp_path / "workspace.lock"
    lock.touch()
    with (
        workspace_lock(lock),
        pytest.raises(RuntimeError, match="still owns"),
        workspace_lock(lock),
    ):
        pytest.fail("Second runner acquired an occupied workspace")
    with workspace_lock(lock):
        pass


def test_frame_parser_handles_split_headers_and_split_lines() -> None:
    reader = DockerFrames()
    data = frame(b'{"event":"session_') + frame(b'started"}\n')
    result = []
    for byte in data:
        result.extend(reader.feed(bytes([byte])))
    assert result == [{"event": "session_started"}]
    assert not reader.buffer and not reader.line


def test_frame_parser_discards_stderr_and_rejects_large_frames() -> None:
    reader = DockerFrames()
    assert reader.feed(frame(b"api_key=secret", 2)) == []
    with pytest.raises(RunnerProtocolError):
        reader.feed(bytes([1, 0, 0, 0]) + (200000).to_bytes(4, "big"))


@pytest.mark.asyncio
async def test_runner_cannot_code_before_controller_commits_native_id(tmp_path: Path) -> None:
    waiting = asyncio.create_task(await_controller("native-1", tmp_path))
    await asyncio.sleep(0)
    assert not waiting.done()
    atomic_json(tmp_path / "start.json", {"native_session_id": "native-1"})
    await asyncio.wait_for(waiting, 1)
    assert json.loads((tmp_path / "start.json").read_text()) == {"native_session_id": "native-1"}


@pytest.mark.asyncio
async def test_runner_rejects_acknowledgement_for_another_session(tmp_path: Path) -> None:
    atomic_json(tmp_path / "start.json", {"native_session_id": "other"})
    with pytest.raises(ValueError, match="another session"):
        await await_controller("native-1", tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("resume", [False, True])
async def test_docker_transport_streams_native_id_before_authorizing_turn(
    tmp_path: Path, resume: bool
) -> None:
    task_id = uuid4()
    workspace = tmp_path / "tasks" / str(task_id) / "repo"
    state = tmp_path / "state" / str(task_id)
    control = tmp_path / "control" / str(task_id) / "lease"
    for directory in (workspace, state, control):
        directory.mkdir(parents=True)
    (control.parent / "workspace.lock").touch()
    mounts = RunnerMounts(
        task_id,
        workspace,
        state,
        control / "task.json",
        tmp_path / "tasks",
        tmp_path / "state",
        tmp_path / "control",
    )
    receipt = TurnReceipt("native-1", "turn-1", "Done", "completed", Usage(20, 4, 5, 0))
    requests = []
    supervision_requests = []

    async def supervise(anomaly):
        supervision_requests.append(anomaly)
        return {"action": "NUDGE", "message": "Use existing formatter"}

    class NativeLogs(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield frame(b'{"event":"session_started","native_session_id":"native-1"}\n')
            # A sub-16KB frame must reach the controller immediately, not be buffered.
            await await_controller("native-1", control)
            yield frame(
                json.dumps(
                    {
                        "event": "supervision_requested",
                        "anomaly": {
                            "sequence": 1,
                            "kind": "TOOL_FAILURE",
                            "detail": "formatter error",
                        },
                    }
                ).encode()
                + b"\n"
            )
            assert json.loads((control / "supervision-1.json").read_text())["action"] == "NUDGE"
            yield frame(
                json.dumps({"event": "turn_completed", "receipt": asdict(receipt)}).encode() + b"\n"
            )

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.startswith("/networks/"):
            return httpx.Response(200, json={"Internal": True})
        if request.url.path == "/containers/create":
            body = json.loads(request.content)
            assert body["HostConfig"]["ReadonlyRootfs"] is True
            assert body["Labels"]["task_id"] == str(task_id)
            return httpx.Response(201, json={"Id": "container-1"})
        if request.url.path.endswith("/logs"):
            return httpx.Response(200, stream=NativeLogs())
        return httpx.Response(204)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://docker"
    ) as client:
        harness = DockerHarness(
            client,
            mounts=mounts,
            manifest=Manifest(
                harness="codex",
                model="gpt-5.6-terra",
                prompt="New task delta",
                max_cost_usd=Decimal(2),
            ),
            image="runner:test",
            network="internal-test",
            environment={"HTTPS_PROXY": "http://proxy:3128"},
            job_id=uuid4(),
            lease_token=uuid4(),
            on_supervision=supervise,
        )
        try:
            if resume:
                await asyncio.wait_for(harness.resume("native-1"), 1)
            else:
                assert await asyncio.wait_for(harness.start(), 1) == "native-1"
            assert not (control / "start.json").exists()
            persisted = json.loads((control / "task.json").read_text())
            assert persisted["native_session_id"] == ("native-1" if resume else None)
            assert await asyncio.wait_for(harness.run_turn("New task delta"), 1) == receipt
        finally:
            await harness.close()
    assert requests[-2].url.path == "/containers/container-1/stop"
    assert requests[-1].method == "DELETE"
    assert len(supervision_requests) == 1
