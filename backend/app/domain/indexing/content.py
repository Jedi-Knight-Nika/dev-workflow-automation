MAX_FILE_BYTES = 200_000


def should_index_content(content: str, max_bytes: int = MAX_FILE_BYTES) -> bool:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    return "\x00" not in content and len(content.encode()) <= max_bytes


def parse_changed_paths(output: str) -> list[str]:
    return sorted({path.strip() for path in output.splitlines() if path.strip()})


def vector_literal(values: list[float], dimensions: int = 1536) -> str:
    if dimensions < 1:
        raise ValueError("dimensions must be positive")
    if len(values) != dimensions:
        raise ValueError(f"Expected {dimensions} embedding dimensions, received {len(values)}")
    return "[" + ",".join(str(value) for value in values) + "]"
