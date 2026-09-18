import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize(
    "source,rule",
    [
        ("import os\n", "F401"),
        ("def read():\n    unused = 1\n    return 2\n", "F841"),
        ("print(missing_name)\n", "F821"),
        ("def read(values=[]):\n    return values\n", "B006"),
        ("for unused in range(3):\n    print('hello')\n", "B007"),
        ("try:\n    int('bad')\nexcept ValueError:\n    raise RuntimeError('bad')\n", "B904"),
        ("import sys\nimport os\n\nprint(sys.version, os.name)\n", "I001"),
        ("from typing import List\n\ndef read() -> List[int]:\n    return []\n", "UP006"),
        ("print('hello')  # noqa: F401\n", "RUF100"),
    ],
)
def test_python_lint_policy_rejects_unsafe_or_unused_code(source, rule):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--config",
            str(BACKEND_ROOT / "pyproject.toml"),
            "--no-cache",
            "--stdin-filename",
            str(BACKEND_ROOT / "app/lint_probe.py"),
            "--output-format",
            "json",
            "-",
        ],
        input=source,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert rule in {message["code"] for message in json.loads(result.stdout)}


@pytest.mark.parametrize(
    "source,error_code",
    [
        ("def untyped(value):\n    return value\n", "no-untyped-def"),
        ('count: int = "wrong"\n', "assignment"),
        ('count: int = "wrong"  # type: ignore\n', "ignore-without-code"),
    ],
)
def test_python_type_policy_is_strict(source, error_code):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(BACKEND_ROOT / "pyproject.toml"),
            "--no-incremental",
            "-c",
            source,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert f"[{error_code}]" in result.stdout
