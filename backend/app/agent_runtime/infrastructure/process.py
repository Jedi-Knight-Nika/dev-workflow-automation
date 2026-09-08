"""Bounded, shell-free output capture for trusted runner plumbing."""

import asyncio
import os
import signal
from collections.abc import Mapping, Sequence
from pathlib import Path


async def capture(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: int = 300,
    output_limit: int = 65536,
) -> bytes:
    if not argv or timeout < 1 or output_limit < 1:
        raise ValueError("Invalid process limits")
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    output = bytearray()
    try:
        async with asyncio.timeout(timeout):
            assert process.stdout
            while block := await process.stdout.read(8192):
                if len(output) + len(block) > output_limit:
                    raise RuntimeError("Operation exceeded its output bound")
                output.extend(block)
            await process.wait()
        if process.returncode:
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
        await process.communicate()
        raise
    return bytes(output)
