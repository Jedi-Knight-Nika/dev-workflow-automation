import asyncio
import os
import signal
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    command: tuple[str, ...]
    exit_code: int | None
    output_tail: str
    timed_out: bool = False

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


async def run_check(
    command: tuple[str, ...], *, workspace: Path, timeout: int = 300, output_limit: int = 16000
) -> CheckResult:
    """Run an administrator-configured argv in the isolated validation runner.

    Never interpolate model output into a shell. Streams are drained while only
    retaining a bounded tail, including when a test produces enormous output.
    """
    if not command or not workspace.is_dir() or timeout < 1 or output_limit < 1:
        raise ValueError("Invalid validation command or limits")
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    tail = bytearray()

    async def drain() -> None:
        assert process.stdout is not None
        while chunk := await process.stdout.read(8192):
            tail.extend(chunk)
            if len(tail) > output_limit:
                del tail[:-output_limit]
        await process.wait()

    timed_out = False
    try:
        async with asyncio.timeout(timeout):
            await drain()
    except (TimeoutError, asyncio.CancelledError) as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
        if isinstance(exc, asyncio.CancelledError):
            raise
        timed_out = True
    return CheckResult(command, process.returncode, tail.decode(errors="replace"), timed_out)
