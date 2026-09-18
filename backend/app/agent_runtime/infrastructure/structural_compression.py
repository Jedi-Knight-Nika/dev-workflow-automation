"""Lossless key-dictionary experiment. Human prose, source and errors stay verbatim."""

from collections import Counter
from typing import Any


def compress(value: dict[str, Any]) -> dict[str, Any]:
    counts: Counter[str] = Counter()

    def count(node: Any, depth: int = 0) -> None:
        if depth > 32:
            raise ValueError("Packet nesting exceeds the compression bound")
        if isinstance(node, dict):
            counts.update(node.keys())
            for child in node.values():
                count(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                count(child, depth + 1)

    count(value)
    dictionary = sorted(
        key for key, count in counts.items() if count >= 2 and 8 <= len(key) <= 200
    )[:128]
    indices = {key: f"~{index}" for index, key in enumerate(dictionary)}

    def pack(node: Any) -> Any:
        if isinstance(node, dict):
            return {
                indices.get(key, "~" + key if key.startswith("~") else key): pack(child)
                for key, child in node.items()
            }
        if isinstance(node, list):
            return [pack(child) for child in node]
        return node

    return {"dictionary": dictionary, "packet": pack(value)}


def decompress(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"dictionary", "packet"}:
        raise ValueError("Invalid compressed packet")
    dictionary = value["dictionary"]
    if (
        not isinstance(dictionary, list)
        or len(dictionary) > 128
        or any(not isinstance(key, str) or not 1 <= len(key) <= 200 for key in dictionary)
        or len(set(dictionary)) != len(dictionary)
    ):
        raise ValueError("Invalid compression dictionary")

    def unpack(node: Any, depth: int = 0) -> Any:
        if depth > 32:
            raise ValueError("Packet nesting exceeds the compression bound")
        if isinstance(node, dict):
            result = {}
            for key, child in node.items():
                if key.startswith("~~"):
                    key = key[1:]
                elif key.startswith("~"):
                    index = key[1:]
                    if (
                        not index.isascii()
                        or not index.isdecimal()
                        or str(int(index)) != index
                        or int(index) >= len(dictionary)
                    ):
                        raise ValueError("Invalid compression reference")
                    key = dictionary[int(index)]
                if key in result:
                    raise ValueError("Duplicate decoded key")
                result[key] = unpack(child, depth + 1)
            return result
        if isinstance(node, list):
            return [unpack(child, depth + 1) for child in node]
        return node

    result = unpack(value["packet"])
    if not isinstance(result, dict):
        raise TypeError("Compressed packet must decode to an object")
    return result
