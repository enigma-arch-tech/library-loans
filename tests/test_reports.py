# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Tests for the report and sorting functions."""

from __future__ import annotations

from datetime import date, timedelta

from core import reports

TODAY = date(2026, 6, 1)


def test_sort_by_title(library):
    titles = [book.title for book in reports.sort_books(library, library.all_books(), "title")]
    assert titles == sorted(titles, key=str.casefold)


def test_sort_by_author_is_case_insensitive(library):
    authors = [book.author for book in reports.sort_books(library, library.all_books(), "author")]
    assert authors == sorted(authors, key=str.casefold)


def test_sort_by_year_puts_unknown_last(library):
    library.add_book("9780131103627", "The C Programming Language", "Brian Kernighan")
    books = reports.sort_books(library, library.all_books(), "year")
    assert books[-1].year is None
    assert books[0].year == 2020


def test_sort_by_status_groups_on_loan(library):
    library.issue_loan("9780132350884", "M0001")
    books = reports.sort_books(library, library.all_books(), "status")
    assert books[-1].isbn == "9780132350884"
    assert books[-1].on_loan is True


def test_sort_by_due_date_puts_available_last(library):
    library.issue_loan("9780596007126", "M0001", TODAY - timedelta(days=2))
    books = reports.sort_books(library, library.all_books(), "due")
    assert books[0].isbn == "9780596007126"
    assert all(not book.on_loan for book in books[1:])


def test_sort_is_stable_for_equal_keys(library):
    # Both "Effective Java..." books share an author.
    books = reports.sort_books(library, library.all_books(), "author")
    titles = [book.title for book in books if book.author == "Joshua Bloch"]
    assert titles == ["Effective Java", "Effective Java, Second Edition"]


def test_overdue_report_excludes_returned_and_on_time(library):
    library.issue_loan("9780132350884", "M0001", TODAY - timedelta(days=30))
    library.issue_loan("9780134685991", "M0002", TODAY - timedelta(days=2))
    library.issue_loan("9780262033848", "M0003", TODAY - timedelta(days=40))
    library.return_loan("9780262033848", TODAY)

    overdue = reports.overdue_loans(library, TODAY)
    assert [loan.isbn for loan in overdue] == ["9780132350884"]


def test_overdue_report_sorted_by_due_date(library):
    library.issue_loan("9780132350884", "M0001", TODAY - timedelta(days=30))
    library.issue_loan("9780134685991", "M0002", TODAY - timedelta(days=40))
    overdue = reports.overdue_loans(library, TODAY)
    assert [loan.isbn for loan in overdue] == ["9780134685991", "9780132350884"]


def test_loans_due_soon_window(library):
    library.issue_loan("9780132350884", "M0001", TODAY - timedelta(days=8))  # due in 6 days
    library.issue_loan("9780134685991", "M0002", TODAY - timedelta(days=20))  # overdue
    due_soon = reports.loans_due_soon(library, 7, TODAY)
    assert [loan.isbn for loan in due_soon] == ["9780132350884"]


def test_most_borrowed_ranks_by_count(library):
    for _ in range(2):
        library.issue_loan("9780132350884", "M0001", TODAY - timedelta(days=5))
        library.return_loan("9780132350884", TODAY - timedelta(days=1))
    library.issue_loan("9780134685991", "M0002")

    ranked = reports.most_borrowed(library, 5)
    assert ranked[0] == (library.get_book("9780132350884"), 2)
    assert ranked[1][1] == 1


def test_availability_summary(library):
    library.issue_loan("9780132350884", "M0001")
    summary = reports.availability_summary(library)
    assert summary["titles"] == 8
    assert summary["on_loan"] == 1
    assert summary["available"] == 7
    assert summary["members"] == 3
    assert summary["active_members"] == 3
    assert summary["active_loans"] == 1
    assert summary["loan_history"] == 1


def test_member_history_newest_first(library):
    library.issue_loan("9780132350884", "M0001", TODAY - timedelta(days=10))
    library.issue_loan("9780134685991", "M0001", TODAY - timedelta(days=2))
    history = reports.member_history(library, "M0001")
    assert [loan.isbn for loan in history] == ["9780134685991", "9780132350884"]


def test_policy_summary_mentions_the_rules():
    text = reports.policy_summary()
    assert "14 days" in text
    assert "grace" in text
