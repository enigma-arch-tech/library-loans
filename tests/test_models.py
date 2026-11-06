# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Tests for validation, the record models and the fine calculation."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.models import (
    GRACE_DAYS,
    FINE_PER_DAY,
    Book,
    Loan,
    ValidationError,
    normalise_isbn,
    parse_date,
    require_email,
    require_text,
    require_year,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("9780132350884", "9780132350884"),
        ("978-0-13-235088-4", "9780132350884"),
        (" 978 0132350884 ", "9780132350884"),
        ("0132350882", "0132350882"),
        ("0-13-235088-2", "0132350882"),
        ("0596007124", "0596007124"),
    ],
)
def test_valid_isbns_are_normalised(raw, expected):
    assert normalise_isbn(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        None,
        "123",
        "9780132350885",  # ISBN-13 check digit wrong
        "0132350881",  # ISBN-10 check digit wrong
        "97801323508X4",  # letters in an ISBN-13
        "abcdefghij",
    ],
)
def test_invalid_isbns_are_rejected(raw):
    with pytest.raises(ValidationError):
        normalise_isbn(raw)


def test_isbn10_with_x_check_digit_is_accepted():
    # 080442957X is a published valid ISBN-10.
    assert normalise_isbn("080442957X") == "080442957X"


def test_require_text_strips_and_rejects_blank():
    assert require_text("  Clean Code  ", "Title") == "Clean Code"
    with pytest.raises(ValidationError):
        require_text("   ", "Title")
    with pytest.raises(ValidationError):
        require_text("x" * 201, "Title")


def test_require_email():
    assert require_email(" a@b.co ") == "a@b.co"
    for bad in ["a@b", "a b@c.com", "@example.com", "a@@b.com"]:
        with pytest.raises(ValidationError):
            require_email(bad)


def test_require_year():
    assert require_year("2008") == 2008
    assert require_year("") is None
    assert require_year(None) is None
    with pytest.raises(ValidationError):
        require_year("12")
    with pytest.raises(ValidationError):
        require_year("not-a-year")


def test_parse_date():
    assert parse_date("2026-11-07") == date(2026, 11, 7)
    assert parse_date(date(2026, 1, 2)) == date(2026, 1, 2)
    with pytest.raises(ValidationError):
        parse_date("07/11/2026")
    with pytest.raises(ValidationError):
        parse_date("")


def test_book_round_trip():
    book = Book("9780132350884", "Clean Code", "Robert C. Martin", 2008)
    assert Book.from_dict(book.to_dict()) == book


def test_member_round_trip():
    from core.models import Member

    member = Member("M0001", "Aisha Khan", "aisha@example.com")
    assert Member.from_dict(member.to_dict()) == member


def test_loan_round_trip():
    loan = Loan("L0001", "9780132350884", "M0001", date(2026, 1, 1), date(2026, 1, 15))
    assert Loan.from_dict(loan.to_dict()) == loan


def test_loan_days_overdue_and_grace():
    due = date(2026, 1, 15)
    loan = Loan("L0001", "9780132350884", "M0001", date(2026, 1, 1), due)
    assert loan.days_overdue(due) == 0
    assert loan.days_overdue(date(2026, 1, 16)) == 1
    assert loan.fine(date(2026, 1, 16)) == 0.0  # inside the grace period
    assert loan.fine(due + timedelta(days=GRACE_DAYS)) == 0.0
    assert loan.fine(date(2026, 1, 19)) == pytest.approx(FINE_PER_DAY)
    assert loan.fine(date(2026, 2, 4)) == pytest.approx(17 * FINE_PER_DAY)


def test_returned_loan_is_never_overdue():
    loan = Loan(
        "L0001",
        "9780132350884",
        "M0001",
        date(2026, 1, 1),
        date(2026, 1, 15),
        returned=date(2026, 1, 20),
    )
    assert loan.days_overdue(date(2026, 3, 1)) == 0
    assert loan.fine(date(2026, 3, 1)) == 0.0
    assert loan.status(date(2026, 3, 1)) == "Returned"


def test_loan_rejects_due_before_issue():
    with pytest.raises(ValidationError):
        Loan.from_dict(
            {
                "loan_id": "L0001",
                "isbn": "9780132350884",
                "member_id": "M0001",
                "issued": "2026-01-10",
                "due": "2026-01-01",
                "returned": None,
            }
        )
