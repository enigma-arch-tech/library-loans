# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Smoke tests for the text interface: menus, one happy path, one error path."""

from __future__ import annotations

import pytest

import cli.main as cli
from core.library import Library


def feed(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> None:
    iterator = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(iterator))


def test_render_table_aligns_columns():
    text = cli.render_table(["A", "BB"], [["x", "y"], ["long", "z"]])
    lines = text.splitlines()
    assert lines[0].startswith("A")
    assert "BB" in lines[0]
    assert "long" in lines[3]


def test_cli_adds_a_book_and_saves(monkeypatch, tmp_path):
    data = tmp_path / "library.json"
    feed(
        monkeypatch,
        [
            "1",  # Books
            "2",  # Add a book
            "9780131103627",
            "The C Programming Language",
            "Brian Kernighan",
            "1978",
            "0",  # back to main menu
            "0",  # exit
        ],
    )
    assert cli.main(["--data", str(data)]) == 0

    reloaded = Library.load(data)
    assert reloaded.get_book("9780131103627").title == "The C Programming Language"


def test_cli_reports_invalid_isbn_without_crashing(monkeypatch, tmp_path, capsys):
    data = tmp_path / "library.json"
    feed(
        monkeypatch,
        [
            "1",
            "2",
            "12345",  # invalid ISBN: accepted by input, rejected by core
            "Bad Book",
            "Nobody",
            "",
            "0",
            "0",
        ],
    )
    assert cli.main(["--data", str(data)]) == 0
    output = capsys.readouterr().out
    assert "Error:" in output
    assert "ISBN" in output
    assert "ISBN 12345" not in Library.load(data).books


def test_cli_issues_and_returns_a_loan(monkeypatch, tmp_path):
    data = tmp_path / "library.json"
    feed(
        monkeypatch,
        [
            "3",  # Loans
            "2",  # Issue
            "9780132350884",
            "M0001",
            "3",  # Return
            "9780132350884",
            "0",
            "0",
        ],
    )
    assert cli.main(["--data", str(data)]) == 0

    reloaded = Library.load(data)
    assert reloaded.active_loans() == []
    assert len(reloaded.loans) == 6  # five sample returns plus this one


def test_cli_demo_runs(capsys):
    assert cli.main(["--demo", "--data", "data/sample_library.json"]) == 0
    output = capsys.readouterr().out
    assert "Overdue report" in output
    assert "Most borrowed" in output
