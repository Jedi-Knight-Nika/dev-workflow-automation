"""Small CONNECT-only gateway for task containers; no keys, DB or Docker socket.

TLS is end-to-end. This gateway restricts destination names/ports, not the content
of an allowed provider request. Run it on both the private runner and egress
networks; task containers belong only to the private network.
"""

import asyncio
import os
import re

ALLOWED = frozenset({"api.openai.com", "api.anthropic.com", "github.com"})
LIMIT = asyncio.Semaphore(64)


def destination(header: bytes) -> str:
    if len(header) > 8192 or not header.endswith(b"\r\n\r\n"):
        raise ValueError("Invalid proxy headers")
    first = header.split(b"\r\n", 1)[0].decode("ascii")
    match = re.fullmatch(r"CONNECT ([a-z0-9.-]+):443 HTTP/1\.[01]", first)
    if not match or match[1] not in ALLOWED:
        raise ValueError("Destination is not allowed")
    return match[1]


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while block := await reader.read(65536):
        writer.write(block)
        await writer.drain()


async def tunnel(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    upstream: asyncio.StreamWriter | None = None
    try:
        async with asyncio.timeout(10):
            header = await reader.readuntil(b"\r\n\r\n")
            host = destination(header)
            await LIMIT.acquire()
        try:
            async with asyncio.timeout(15):
                remote, upstream = await asyncio.open_connection(host, 443)
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            async with asyncio.timeout(7200):
                tasks = {
                    asyncio.create_task(relay(reader, upstream)),
                    asyncio.create_task(relay(remote, writer)),
                }
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            LIMIT.release()
    except (
        ValueError,
        UnicodeError,
        OSError,
        TimeoutError,
        asyncio.IncompleteReadError,
        asyncio.LimitOverrunError,
    ):
        if upstream is None:
            writer.write(
                b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
            )
    finally:
        if upstream:
            upstream.close()
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


async def main() -> None:
    server = await asyncio.start_server(
        tunnel, "0.0.0.0", int(os.environ.get("PROXY_PORT", "3128")), limit=8192
    )
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
