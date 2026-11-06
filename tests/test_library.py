# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Tests for the library aggregate: rules, state and persistence."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.library import Library
from core.models import (
    LOAN_PERIOD_DAYS,
    MAX_ACTIVE_LOANS,
    DuplicateError,
    LoanError,
    NotFoundError,
    ValidationError,
)

ISBN = "9780132350884"
OTHER = "9780134685991"


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def test_add_book_normalises_isbn(library):
    book = library.add_book("978-0-13-110362-7", "The C Programming Language", "Brian Kernighan")
    assert book.isbn == "9780131103627"
    assert library.books["9780131103627"].title == "The C Programming Language"


def test_add_book_rejects_duplicate(library):
    with pytest.raises(DuplicateError):
        library.add_book(ISBN, "Another title", "Someone")


def test_add_book_rejects_invalid_isbn(library):
    with pytest.raises(ValidationError):
        library.add_book("1234567890", "Bad", "Bad")


def test_get_book_unknown_isbn(library):
    with pytest.raises(NotFoundError):
        library.get_book("9780131103627")


def test_update_book_changes_fields(library):
    original = library.get_book(ISBN)
    updated = library.update_book(ISBN, title="Clean Code (2nd)", year=2010)
    assert updated is original
    assert updated.title == "Clean Code (2nd)"
    assert updated.year == 2010
    # The search index follows the new title.
    assert library.search_books("2nd") == [updated]


def test_update_book_with_blank_title_is_rejected(library):
    with pytest.raises(ValidationError):
        library.update_book(ISBN, title="   ")


def test_update_book_can_clear_the_year(library):
    assert library.get_book(ISBN).year == 2008
    library.update_book(ISBN, year=None)
    assert library.get_book(ISBN).year is None


def test_update_book_leaves_unsent_fields_alone(library):
    library.update_book(ISBN, author="Uncle Bob")
    book = library.get_book(ISBN)
    assert book.author == "Uncle Bob"
    assert book.title == "Clean Code"
    assert book.year == 2008


def test_remove_book_without_history(library):
    library.remove_book(ISBN)
    assert ISBN not in library.books
    assert library.search_books("clean") == []


def test_remove_book_on_loan_is_blocked(library):
    library.issue_loan(ISBN, "M0001")
    with pytest.raises(LoanError):
        library.remove_book(ISBN)


def test_remove_book_with_history_is_blocked(library):
    library.issue_loan(ISBN, "M0001", date.today() - timedelta(days=20))
    library.return_loan(ISBN)
    with pytest.raises(LoanError):
        library.remove_book(ISBN)


# ---------------------------------------------------------------------------
# Membership
# ---------------------------------------------------------------------------


def test_member_ids_are_generated_in_sequence(library):
    assert [m.member_id for m in library.all_members()] == ["M0001", "M0002", "M0003"]
    member = library.add_member("Dev Patel", "dev.patel@example.com")
    assert member.member_id == "M0004"


def test_add_member_rejects_duplicate_email(library):
    with pytest.raises(DuplicateError):
        library.add_member("Someone Else", "AISHA.KHAN@example.com")


def test_add_member_rejects_bad_email(library):
    with pytest.raises(ValidationError):
        library.add_member("No Email", "not-an-email")


def test_update_member_rejects_email_clash(library):
    with pytest.raises(DuplicateError):
        library.update_member("M0001", email="ben.okafor@example.com")


def test_remove_member_without_history(library):
    library.remove_member("M0003")
    assert "M0003" not in library.members


def test_remove_member_with_history_is_blocked(library):
    library.issue_loan(ISBN, "M0002")
    library.return_loan(ISBN)
    with pytest.raises(LoanError):
        library.remove_member("M0002")


# ---------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------


def test_issue_loan_sets_state_and_due_date(library):
    issued = date(2026, 3, 2)
    loan = library.issue_loan(ISBN, "M0001", issued)
    assert loan.due == issued + timedelta(days=LOAN_PERIOD_DAYS)
    assert loan.is_active
    assert library.get_book(ISBN).on_loan is True
    assert library.active_loans_for_member("M0001") == [loan]


def test_issue_loan_rejects_book_already_on_loan(library):
    library.issue_loan(ISBN, "M0001")
    with pytest.raises(LoanError):
        library.issue_loan(ISBN, "M0002")


def test_issue_loan_rejects_inactive_member(library):
    library.update_member("M0003", active=False)
    with pytest.raises(LoanError):
        library.issue_loan(ISBN, "M0003")


def test_issue_loan_rejects_unknown_member(library):
    with pytest.raises(NotFoundError):
        library.issue_loan(ISBN, "M9999")


def test_issue_loan_rejects_future_date(library):
    with pytest.raises(ValidationError):
        library.issue_loan(ISBN, "M0001", date.today() + timedelta(days=1))


def test_member_loan_limit_is_enforced(library, isbns):
    for isbn in isbns[:MAX_ACTIVE_LOANS]:
        library.issue_loan(isbn, "M0001")
    with pytest.raises(LoanError):
        library.issue_loan(isbns[MAX_ACTIVE_LOANS], "M0001")


def test_return_loan_closes_it_and_frees_the_book(library):
    library.issue_loan(ISBN, "M0001", date(2026, 1, 1))
    loan = library.return_loan(ISBN, date(2026, 1, 10))
    assert loan.returned == date(2026, 1, 10)
    assert library.get_book(ISBN).on_loan is False
    assert library.active_loans() == []


def test_return_loan_rejects_date_before_issue(library):
    library.issue_loan(ISBN, "M0001", date(2026, 1, 10))
    with pytest.raises(ValidationError):
        library.return_loan(ISBN, date(2026, 1, 1))


def test_return_loan_twice_is_rejected(library):
    library.issue_loan(ISBN, "M0001")
    library.return_loan(ISBN)
    with pytest.raises(LoanError):
        library.return_loan(ISBN)


def test_renew_loan_extends_due_date(library):
    loan = library.issue_loan(ISBN, "M0001", date.today())
    before = loan.due
    renewed = library.renew_loan(ISBN)
    assert renewed.due == before + timedelta(days=LOAN_PERIOD_DAYS)


def test_renew_overdue_loan_is_blocked(library):
    loan = library.issue_loan(ISBN, "M0001", date.today() - timedelta(days=LOAN_PERIOD_DAYS + 1))
    assert loan.due < date.today()
    with pytest.raises(LoanError):
        library.renew_loan(ISBN)


def test_loan_ids_increment(library):
    first = library.issue_loan(ISBN, "M0001")
    second = library.issue_loan(OTHER, "M0001")
    assert (first.loan_id, second.loan_id) == ("L0001", "L0002")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_by_title_is_case_insensitive(library):
    assert [book.isbn for book in library.search_books("clean")] == [ISBN]


def test_search_by_author(library):
    results = library.search_books("BLOCH")
    assert [book.isbn for book in results] == ["9780134685991", "9780321356680"]


def test_search_by_partial_word(library):
    assert [book.title for book in library.search_books("corm")] == [
        "Introduction to Algorithms"
    ]


def test_search_by_isbn_fragment(library):
    results = library.search_books("978013")
    assert {book.isbn for book in results} == {"9780132350884", "9780134685991"}


def test_search_with_no_matches(library):
    assert library.search_books("zzzz") == []


def test_empty_search_returns_everything_sorted(library):
    results = library.search_books("  ")
    assert len(results) == len(library.books)
    assert [book.title for book in results] == sorted(
        (book.title for book in library.books.values()), key=str.casefold
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_and_reload_keeps_state(library, tmp_path):
    library.issue_loan(ISBN, "M0001")
    path = tmp_path / "library.json"
    library.save(path)

    reloaded = Library.load(path)
    assert reloaded.to_dict() == library.to_dict()
    assert reloaded.get_book(ISBN).on_loan is True
    assert reloaded.active_loans()[0].member_id == "M0001"


def test_load_derives_availability_from_history(library):
    raw = library.to_dict()
    raw["books"][0]["on_loan"] = True  # contradict the (empty) loan history
    reloaded = Library.from_dict(raw)
    assert reloaded.books[raw["books"][0]["isbn"]].on_loan is False


def test_load_rejects_loan_for_unknown_book(library):
    raw = library.to_dict()
    raw["loans"] = [
        {
            "loan_id": "L0001",
            "isbn": "9780131103627",
            "member_id": "M0001",
            "issued": "2026-01-01",
            "due": "2026-01-15",
            "returned": None,
        }
    ]
    with pytest.raises(ValidationError):
        Library.from_dict(raw)


def test_load_rejects_loan_for_unknown_member(library):
    raw = library.to_dict()
    raw["loans"] = [
        {
            "loan_id": "L0001",
            "isbn": ISBN,
            "member_id": "M9999",
            "issued": "2026-01-01",
            "due": "2026-01-15",
            "returned": None,
        }
    ]
    with pytest.raises(ValidationError):
        Library.from_dict(raw)


def test_borrowing_counts(library):
    library.issue_loan(ISBN, "M0001")
    library.return_loan(ISBN)
    library.issue_loan(ISBN, "M0001")
    assert library.borrowing_counts()["M0001"] == 2
