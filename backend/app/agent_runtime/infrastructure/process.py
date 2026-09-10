"""Bounded, shell-free output capture for trusted runner plumbing."""

import asyncio
import os
import signal
from collections.abc import Mapping, Sequence
from pathlib import Path


async def _drain_diagnostic(stream: asyncio.StreamReader, limit: int) -> bytes:
    """Keep a bounded prefix while draining the pipe so writers cannot block."""
    output = bytearray()
    while block := await stream.read(8192):
        remaining = limit - len(output)
        if remaining > 0:
            output.extend(block[:remaining])
    return bytes(output)


async def capture(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = 300,
    output_limit: int = 65536,
    include_stderr: bool = False,
) -> bytes:
    if not argv or timeout < 1 or output_limit < 1:
        raise ValueError("Invalid process limits")
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE if include_stderr else asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    output = bytearray()
    stderr_task = (
        asyncio.create_task(_drain_diagnostic(process.stderr, output_limit))
        if include_stderr and process.stderr
        else None
    )
    try:
        async with asyncio.timeout(timeout):
            assert process.stdout
            while block := await process.stdout.read(8192):
                if len(output) + len(block) > output_limit:
                    raise RuntimeError("Operation exceeded its output bound")
                output.extend(block)
            await process.wait()
            diagnostic = await stderr_task if stderr_task else b""
        if process.returncode:
            if stderr_task:
                detail = diagnostic.decode("utf-8", "replace")
                detail = " ".join(detail.split())[:1000]
                raise RuntimeError(f"Operation failed: {detail or 'no diagnostic output'}")
            raise RuntimeError("Operation failed; raw stderr withheld")
    except BaseException:
        # Git can spawn transport helpers. Cancellation must stop the group,
        # even if the main process exited while a helper still holds stdout.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        # Drain the already-buffered pipe after killing all writers. wait()
        # alone can deadlock when asyncio paused reading a full stdout buffer.
        if stderr_task:
            stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)
        await process.communicate()
        raise
    return bytes(output)
