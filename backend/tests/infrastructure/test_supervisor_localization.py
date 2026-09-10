from app.supervisor.infrastructure import localization


def test_flat_directory_cannot_exceed_inventory_scan_limit(tmp_path, monkeypatch):
    files = [f"{index:04}.lock" for index in range(4000)] + ["target.py"]
    monkeypatch.setattr(localization.os, "walk", lambda *a, **kw: [(str(tmp_path), [], files)])
    assert localization.repository_paths(tmp_path) == []
    assert localization.candidate_paths(tmp_path, "target") == []


def test_candidate_selection_keeps_score_order_and_lexical_ties(tmp_path, monkeypatch):
    files = [f"target_{index:02}.py" for index in range(12)] + ["target_widget.py"]
    monkeypatch.setattr(
        localization.os, "walk", lambda *a, **kw: [(str(tmp_path), [], list(reversed(files)))]
    )
    assert localization.candidate_paths(tmp_path, "target widget") == [
        "target_widget.py",
        *[f"target_{index:02}.py" for index in range(7)],
    ]
