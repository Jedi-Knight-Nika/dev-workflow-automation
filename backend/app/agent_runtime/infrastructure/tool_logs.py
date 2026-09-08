"""Protected native-state evidence, never sent to the API or metric labels."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class ToolLogs:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.written = sum(p.stat().st_size for p in root.glob("*.log")) if root.exists() else 0
        self.sizes: dict[str, int] = {}

    def append(self, identifier: str, text: str | bytes) -> str:
        key = hashlib.sha256(identifier.encode()).hexdigest()
        data = text.encode() if isinstance(text, str) else text
        # Stop execution on audit exhaustion, rather than silently discarding evidence.
        if self.written + len(data) > 100_000_000:
            raise RuntimeError("Task tool-log allowance exhausted")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.root / (key + ".log")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "ab") as stream:
            stream.write(data)
        self.written += len(data)
        self.sizes[key] = self.sizes.get(key, 0) + len(data)
        return str(path)

    def result(self, identifier: str, result: Any, cap: int) -> Any:
        serialized = json.dumps(result, ensure_ascii=True)
        path = self.append(identifier, serialized)
        self.finish(identifier, {"source": "native-tool-hook"})

        def bounded(value: Any) -> Any:
            if isinstance(value, str):
                # Byte cap is conservative for unknown native tokenizers.
                data = value.encode()
                if len(data) <= cap:
                    return value
                return (
                    data[-cap:].decode(errors="replace")
                    + f"\n[truncated; full native tool result: {path}]"
                )
            if isinstance(value, dict):
                return {key: bounded(item) for key, item in value.items()}
            if isinstance(value, list):
                return [bounded(item) for item in value]
            return value

        return bounded(result)

    def finish(self, identifier: str, metadata: dict[str, Any]) -> None:
        key = hashlib.sha256(identifier.encode()).hexdigest()
        path = self.root / (key + ".log")
        if not path.is_file() or path.is_symlink():
            return
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(65536):
                digest.update(block)
        payload = {**metadata, "sha256": digest.hexdigest(), "byte_length": path.stat().st_size}
        descriptor = os.open(
            self.root / (key + ".json"),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "w") as stream:
            json.dump(payload, stream)
