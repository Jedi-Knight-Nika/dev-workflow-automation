import json
import sys
from pathlib import Path

import pytest

from app.agent_runtime.infrastructure.bounded_command import run
from app.agent_runtime.infrastructure.repository_tools import formatter_command, investigate


def test_formatter_uses_frontend_cwd_and_rejects_escape(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    (frontend / "node_modules/.bin").mkdir(parents=True)
    (frontend / "node_modules/.bin/prettier").touch()
    (frontend / "Window.svelte").touch()
    cwd, argv = formatter_command(tmp_path, ["frontend/Window.svelte"])
    assert cwd == frontend and argv[1:] == ["--write", "./Window.svelte"]
    (tmp_path / "outside.svelte").touch()
    (frontend / "escape.svelte").symlink_to(tmp_path / "outside.svelte")
    for path in ["outside.svelte", "frontend/escape.svelte", "frontend/node_modules/.bin/prettier"]:
        with pytest.raises(ValueError):
            formatter_command(tmp_path, [path])


def test_investigation_is_bounded_and_explicitly_truncated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "LiveExecution.svelte").write_text("x" * 20000)
    result = investigate(tmp_path, "LIVE EXECUTION გადაადგილება")
    assert result["candidate_paths"] == ["LiveExecution.svelte"]
    assert result["source_slices"][0]["truncated"]
    assert len(result["source_slices"][0]["text"]) == 1800


def test_syntax_map_finds_symbol_importer_and_invalidates_dirty_cache(tmp_path: Path) -> None:
    from app.agent_runtime.infrastructure.repo_index import investigate

    (tmp_path / "Panel.ts").write_text("export function resizeWindow() { return 1; }")
    (tmp_path / "Consumer.ts").write_text("import {resizeWindow} from './Panel'; resizeWindow();")
    cache = tmp_path / ".cache"
    first = investigate(tmp_path, "resizeWindow", cache)
    panel = next(r for r in first["repo_map"] if r["path"] == "Panel.ts")
    assert panel["symbols"][0]["name"] == "resizeWindow"
    assert "Consumer.ts" in panel["candidate_callers"]
    (tmp_path / "Panel.ts").write_text("export function moveWindow() { return 2; }")
    second = investigate(tmp_path, "moveWindow", cache)
    assert second["repo_map"][0]["symbols"][0]["name"] == "moveWindow"


def test_map_only_investigation_skips_unused_source_reads(tmp_path, monkeypatch):
    from app.agent_runtime.infrastructure.repo_index import investigate

    source = tmp_path / "Panel.ts"
    source.write_text("export function resizeWindow() { return 1; }")
    cache = tmp_path / ".cache"
    complete = investigate(tmp_path, "resizeWindow", cache)
    original_read = Path.read_text

    def read_text(path, *args, **kwargs):
        assert path != source, "Map-only lookup should not reread source slices"
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    mapped = investigate(tmp_path, "resizeWindow", cache, include_source_slices=False)
    assert mapped == {**complete, "source_slices": []}


@pytest.mark.parametrize("cached", ["null", "[]", '"invalid"', "{broken json"])
def test_repository_index_rebuilds_invalid_cache_roots(tmp_path, cached):
    from app.agent_runtime.infrastructure.repo_index import investigate

    (tmp_path / "Panel.ts").write_text("export function resizeWindow() { return 1; }")
    cache = tmp_path / ".cache"
    cache.mkdir()
    (cache / "index.json").write_text(cached)
    result = investigate(tmp_path, "resizeWindow", cache)
    assert result["candidate_paths"] == ["Panel.ts"]
    saved = json.loads((cache / "index.json").read_text())
    assert saved["files"][0]["path"] == "Panel.ts"


def test_investigation_reads_source_once_for_index_phrases_and_slices(tmp_path, monkeypatch):
    from app.agent_runtime.infrastructure.repo_index import investigate

    source = tmp_path / "startup.html"
    source.write_text("<p>Starting local stack please wait here</p>")
    cache = tmp_path / ".cache"
    read_bytes, read_text = Path.read_bytes, Path.read_text
    reads = []

    def bytes_read(path):
        if path == source:
            reads.append(path)
        return read_bytes(path)

    def text_read(path, *args, **kwargs):
        assert path != source, "Source already exists in the current scan snapshot"
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", bytes_read)
    monkeypatch.setattr(Path, "read_text", text_read)
    for expected_reads in (1, 2):
        result = investigate(tmp_path, "Starting local stack please wait here", cache)
        assert result["candidate_paths"] == ["startup.html"]
        assert "Starting local stack" in result["source_slices"][0]["text"]
        assert len(reads) == expected_reads


@pytest.mark.asyncio
async def test_bounded_logs_keep_failure_status_full_output_and_cwd(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    code = await run(
        [
            sys.executable,
            "-c",
            "import os; print(os.getcwd()); print('x' * 20000); raise SystemExit(7)",
        ],
        cwd=tmp_path,
    )
    result = json.loads(capsys.readouterr().out)
    assert code == result["exit_code"] == 7 and result["truncated"]
    assert len(result["stdout_tail"]) <= 6000
    assert str(tmp_path) in Path(result["full_log_path"]).read_text()
    assert Path(result["full_log_path"]).stat().st_size == result["byte_length"]


@pytest.mark.asyncio
async def test_silent_command_still_has_auditable_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert await run([sys.executable, "-c", "pass"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["full_log_path"]).is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_size,exit_code", [(10, 0), (350, 1)])
async def test_command_tail_retains_bytes_across_many_small_reads(
    tmp_path, monkeypatch, chunk_size, exit_code
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.agent_runtime.infrastructure import bounded_command

    monkeypatch.setenv("HOME", str(tmp_path))
    chunks = [bytes([65 + i]) * chunk_size for i in range(20)]
    process = SimpleNamespace(
        stdout=SimpleNamespace(read=AsyncMock(side_effect=[*chunks, b""])),
        wait=AsyncMock(return_value=exit_code),
    )
    monkeypatch.setattr(
        bounded_command.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    result = await bounded_command.capture_command(["test-command"], cwd=tmp_path)
    output = b"".join(chunks)
    cap = 6000 if exit_code else 4000
    assert result["stdout_tail"] == output[-cap:].decode()
    assert result["truncated"] == (len(output) > cap)
    log = Path(result["full_log_path"])
    assert log.read_bytes() == output
    metadata = json.loads(log.with_suffix(".json").read_text())
    assert metadata["duration_ms"] == result["duration_ms"]
    assert metadata["exit_code"] == result["exit_code"] == exit_code


@pytest.mark.asyncio
async def test_combined_check_uses_file_lint_and_keeps_individual_failures(tmp_path, monkeypatch):
    from app.agent_runtime.infrastructure import repository_tools as module

    frontend = tmp_path / "frontend"
    (frontend / "node_modules/.bin").mkdir(parents=True)
    (frontend / "node_modules/.bin/prettier").touch()
    (frontend / "Window.svelte").touch()
    calls = []

    async def capture(argv, *, cwd):
        assert cwd == frontend
        calls.append(argv)
        if "eslint" in argv[0]:
            assert argv[1:] == ["--format", "json", "./Window.svelte"]
            return {
                "exit_code": 1,
                "stdout_tail": json.dumps(
                    [
                        {
                            "filePath": str(frontend / "Window.svelte"),
                            "messages": [
                                {
                                    "severity": 2,
                                    "line": 4,
                                    "ruleId": "@typescript-eslint/no-unused-vars",
                                    "message": "x unused",
                                }
                            ],
                        }
                    ]
                ),
                "full_log_path": "lint.log",
            }
        assert len(calls) == 1 or "--write" in calls[0]
        return {"exit_code": 0, "stdout_tail": "pass", "full_log_path": "pass.log"}

    monkeypatch.setattr(module, "capture_command", capture)
    result = await module.check_frontend(tmp_path, ["frontend/Window.svelte"])
    assert result["exit_code"] == 1 and len(calls) == 3
    assert result["checks"][2]["errors"][0]["line"] == 4
    assert result["checks"][2]["full_log_path"] == "lint.log"


def test_minor_recovery_rejects_stale_missing_or_infrastructure_evidence():
    from copy import deepcopy

    from app.agent_runtime.infrastructure.bounded_recovery import minor_lint_errors

    path = "frontend/src/Window.svelte"
    facts = {"changed_files": [path], "diff_fingerprint": "current"}
    evidence = {
        "paths": [path],
        "diff_fingerprint": "current",
        "checks": [
            {"name": "format", "exit_code": 0},
            {"name": "typecheck", "exit_code": 0},
            {
                "name": "lint",
                "exit_code": 1,
                "error_count": 1,
                "errors": [
                    {
                        "path": path,
                        "line": 4,
                        "rule": "@typescript-eslint/no-unused-vars",
                        "message": "x unused",
                    }
                ],
            },
        ],
    }
    assert len(minor_lint_errors(evidence, facts)) == 1
    assert not minor_lint_errors(None, facts)
    assert not minor_lint_errors({**evidence, "diff_fingerprint": "old"}, facts)
    bad = deepcopy(evidence)
    bad["checks"][1]["exit_code"] = 1
    assert not minor_lint_errors(bad, facts)
    assert not minor_lint_errors(evidence, {**facts, "changed_files": []})


def test_lint_evidence_rejects_partial_malformed_and_outside_reports(tmp_path):
    from app.agent_runtime.infrastructure.repository_tools import lint_evidence

    for result in (
        {"stdout_tail": "[]", "truncated": True},
        {"stdout_tail": "not json"},
        {"stdout_tail": '[{"messages": [null]}]'},
        {
            "stdout_tail": json.dumps(
                [{"filePath": "/outside.ts", "messages": [{"severity": 2, "message": "bad"}]}]
            )
        },
    ):
        assert lint_evidence(tmp_path, result) == {}
    assert lint_evidence(tmp_path, {"stdout_tail": "[]"}) == {"errors": [], "error_count": 0}


def test_validation_candidate_requires_matching_complete_successful_checks():
    from app.agent_runtime.infrastructure.bounded_recovery import checks_passed

    facts = {"diff_fingerprint": "current", "changed_files": ["frontend/src/Window.svelte"]}
    evidence = {
        "diff_fingerprint": "current",
        "paths": facts["changed_files"],
        "checks": [{"name": name, "exit_code": 0} for name in ("format", "typecheck", "lint")],
    }
    assert checks_passed(evidence, facts)
    assert not checks_passed(None, facts)
    assert not checks_passed({**evidence, "diff_fingerprint": "old"}, facts)
    assert not checks_passed(evidence, {**facts, "changed_files": []})
    assert not checks_passed(evidence, {**facts, "changed_files": ["other"]})
    assert not checks_passed({**evidence, "checks": evidence["checks"][:2]}, facts)
    evidence["checks"][2]["exit_code"] = 1
    assert not checks_passed(evidence, facts)
