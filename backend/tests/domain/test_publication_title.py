import pytest

from app.engineering.domain.publication_title import publication_title


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("add smoke cursor effect", "chore: add smoke cursor effect"),
        ("feat: add smoke cursor effect", "feat: add smoke cursor effect"),
        ("fix(ui): correct cursor position", "fix(ui): correct cursor position"),
        ("feat(api)!: remove old endpoint", "feat(api)!: remove old endpoint"),
        ("docs: update setup", "docs: update setup"),
        ("  fix:  handle\nerrors\x00 safely ", "fix: handle errors safely"),
        ("კურსორის გაუმჯობესება", "chore: update task implementation"),
        ("\n\x00", "chore: update task"),
        ("fix:", "chore: fix:"),
    ],
)
def test_publication_title(title: str, expected: str) -> None:
    assert publication_title(title) == expected


@pytest.mark.parametrize("title", ["x" * 500, "feat(ui)!: " + "ა" * 500])
def test_subject_is_bounded_and_idempotent(title: str) -> None:
    result = publication_title(title)
    assert len(result) <= 72
    assert publication_title(result) == result


def test_english_developer_title_and_descriptive_body() -> None:
    from app.engineering.domain.publication_title import publication_body

    summary = "IMPLEMENTED\nfeat(desktop): add branded startup loader\n- Animate the diamond.\n- Preserve startup behavior."
    title = publication_title("ქართული დავალება", summary)
    assert title == "feat(desktop): add branded startup loader"
    body = publication_body(
        task_ref="TRELLO-test",
        title=title,
        summary=summary,
        sha="abc",
        change_context="desktop/src/index.html | 10 +",
        checks=[["npm", "test"]],
    )
    assert "Animate the diamond" in body and "## Changed files" in body
    assert "`npm test` — passed" in body
    assert "IMPLEMENTED" not in body
