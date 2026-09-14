import hashlib
import subprocess

import pytest

from app.agent_runtime.infrastructure.patch_tools import apply_edits
from app.agent_runtime.infrastructure.prompt_cache import prompt_cache_settings


def test_exact_edits_generate_diff_and_preserve_missing_newline(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = tmp_path / "theme.ts"
    path.write_text("const theme = 'dark';")
    hashes = {"theme.ts": hashlib.sha256(path.read_bytes()).hexdigest(), "docs/new.md": "MISSING"}
    edits = [
        {"path": "theme.ts", "old_text": "'dark'", "new_text": "readTheme()"},
        {"path": "docs/new.md", "old_text": "", "new_text": "# Theme\n"},
    ]
    assert apply_edits(tmp_path, edits, hashes) == ["docs/new.md", "theme.ts"]
    assert path.read_text() == "const theme = readTheme();"
    assert (tmp_path / "docs/new.md").read_text() == "# Theme\n"
    with pytest.raises(ValueError, match="source changed"):
        apply_edits(tmp_path, edits, hashes)


def test_bad_second_edit_leaves_first_file_unchanged(tmp_path):
    path = tmp_path / "theme.ts"
    path.write_text("dark dark\n")
    hashes = {"theme.ts": hashlib.sha256(path.read_bytes()).hexdigest()}
    with pytest.raises(ValueError, match="matched 2 times"):
        apply_edits(
            tmp_path,
            [
                {"path": "theme.ts", "old_text": "dark dark", "new_text": "light light"},
                {"path": "theme.ts", "old_text": "light", "new_text": "dark"},
            ],
            hashes,
        )
    assert path.read_text() == "dark dark\n"


def test_cache_key_tracks_contract_not_task():
    first = prompt_cache_settings("gpt-5.6-terra", "stable contract")
    assert first == prompt_cache_settings("gpt-5.6-terra", "stable contract")
    assert first != prompt_cache_settings("gpt-5.6-terra", "changed contract")
    assert first["prompt_cache_options"]["ttl"] == "30m"
