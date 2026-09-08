"""Runner-local shell wrapper: full evidence on disk, bounded model-visible output.

Native agents still choose and execute their own tools. This wrapper is for noisy
checks/builds; it neither patches source nor receives controller credentials.
"""

import asyncio
import hashlib
import json
import os
import signal
import sys
from collections import deque
from pathlib import Path
from time import monotonic
from uuid import uuid4

from app.agent_runtime.infrastructure.tool_logs import ToolLogs


async def run(argv: list[str]) -> int:
    if not argv:
        raise ValueError("Provide an executable and argv after --")
    root = Path.home() / ".aew" / "tool-logs"
    logs = ToolLogs(root)
    identifier = "command-" + uuid4().hex
    tail: deque[bytes] = deque(maxlen=8)
    started = monotonic()
    environment = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TERM"}
    }
    process = await asyncio.create_subprocess_exec(
        *argv,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    path = ""
    size = 0
    try:
        async with asyncio.timeout(300):
            assert process.stdout
            while data := await process.stdout.read(4096):
                size += len(data)
                tail.append(data)
                path = logs.append(identifier, data)
            code = await process.wait()
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.communicate()
        raise
    cap = 6000 if code else 4000  # Conservative bytes, not a fabricated exact tokenizer count.
    logs.finish(
        identifier,
        {
            "exit_code": code,
            "duration_ms": round((monotonic() - started) * 1000),
            "command_sha256": hashlib.sha256(json.dumps(argv).encode()).hexdigest(),
            "source": "full-process-output",
        },
    )
    print(
        json.dumps(
            {
                "exit_code": code,
                "duration_ms": round((monotonic() - started) * 1000),
                "stdout_tail": b"".join(tail)[-cap:].decode(errors="replace"),
                "truncated": size > cap,
                "full_log_path": path,
                "byte_length": size,
            }
        )
    )
    return code


def main() -> None:
    argv = sys.argv[1:]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    raise SystemExit(asyncio.run(run(argv)))


if __name__ == "__main__":
    main()
