# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Domain models, validation rules and business constants.

Data structures
---------------
``Book``, ``Member`` and ``Loan`` are immutable-in-spirit value objects backed by
``dataclasses``. Collections of them live in ``core.library.Library``.

All validation raises a subclass of ``LibraryError`` so that the front ends can
present a friendly message without knowing anything about the domain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Business rules (single source of truth for both front ends)
# ---------------------------------------------------------------------------

LOAN_PERIOD_DAYS = 14
MAX_ACTIVE_LOANS = 5
GRACE_DAYS = 3
FINE_PER_DAY = 0.15
MIN_PUBLICATION_YEAR = 1450


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LibraryError(Exception):
    """Base class for every expected, user-facing error."""


class ValidationError(LibraryError):
    """Input failed a validation rule."""


class DuplicateError(LibraryError):
    """A record with the same natural key already exists."""


class NotFoundError(LibraryError):
    """A requested record does not exist."""


class LoanError(LibraryError):
    """A loan operation is not allowed in the current state."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_ISBN_SEPARATORS = re.compile(r"[-\s]")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_isbn(raw: Any) -> str:
    """Return a validated ISBN-10/ISBN-13 with separators removed.

    Raises ``ValidationError`` when the value is missing, the wrong length or
    fails the published check-digit calculation.
    """
    if raw is None:
        raise ValidationError("ISBN is required.")
    cleaned = _ISBN_SEPARATORS.sub("", str(raw)).upper()
    if not cleaned:
        raise ValidationError("ISBN is required.")

    if len(cleaned) == 10:
        _check_isbn10(cleaned)
    elif len(cleaned) == 13:
        _check_isbn13(cleaned)
    else:
        raise ValidationError(
            f"ISBN must have 10 or 13 digits (got {len(cleaned)} characters)."
        )
    return cleaned


def _check_isbn10(isbn: str) -> None:
    if not isbn[:9].isdigit() or not (isbn[9].isdigit() or isbn[9] == "X"):
        raise ValidationError("ISBN-10 must contain digits, with X allowed only last.")
    total = sum((10 - index) * int(char) for index, char in enumerate(isbn[:9]))
    total += 10 if isbn[9] == "X" else int(isbn[9])
    if total % 11 != 0:
        raise ValidationError("ISBN-10 check digit is not valid.")


def _check_isbn13(isbn: str) -> None:
    if not isbn.isdigit():
        raise ValidationError("ISBN-13 must contain digits only.")
    total = sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(isbn))
    if total % 10 != 0:
        raise ValidationError("ISBN-13 check digit is not valid.")


def require_text(value: Any, field: str, max_length: int = 200) -> str:
    """Return ``value`` stripped, or raise if it is empty/too long."""
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValidationError(f"{field} is required.")
    if len(text) > max_length:
        raise ValidationError(f"{field} must be {max_length} characters or fewer.")
    return text


def require_email(value: Any) -> str:
    email = require_text(value, "Email", 120)
    if not _EMAIL.match(email):
        raise ValidationError("Email address is not valid.")
    return email


def require_year(value: Any) -> int | None:
    """Validate an optional publication year."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        raise ValidationError("Year must be a whole number.") from None
    if not MIN_PUBLICATION_YEAR <= year <= date.today().year + 1:
        raise ValidationError(
            f"Year must be between {MIN_PUBLICATION_YEAR} and {date.today().year + 1}."
        )
    return year


def parse_date(value: Any, field: str = "Date") -> date:
    """Parse an ISO ``YYYY-MM-DD`` string (or pass a ``date`` through)."""
    if isinstance(value, date):
        return value
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValidationError(f"{field} is required (YYYY-MM-DD).")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValidationError(f"{field} must use the format YYYY-MM-DD.") from None


def _parse_optional_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    return parse_date(value, field)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class Book:
    isbn: str
    title: str
    author: str
    year: int | None = None
    on_loan: bool = False

    @property
    def status(self) -> str:
        return "On loan" if self.on_loan else "Available"

    def to_dict(self) -> dict[str, Any]:
        return {
            "isbn": self.isbn,
            "title": self.title,
            "author": self.author,
            "year": self.year,
            "on_loan": self.on_loan,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Book":
        return cls(
            isbn=normalise_isbn(raw.get("isbn")),
            title=require_text(raw.get("title"), "Title"),
            author=require_text(raw.get("author"), "Author"),
            year=require_year(raw.get("year")),
            on_loan=bool(raw.get("on_loan", False)),
        )


@dataclass
class Member:
    member_id: str
    name: str
    email: str
    active: bool = True

    @property
    def status(self) -> str:
        return "Active" if self.active else "Inactive"

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_id": self.member_id,
            "name": self.name,
            "email": self.email,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Member":
        return cls(
            member_id=require_text(raw.get("member_id"), "Member ID", 20).upper(),
            name=require_text(raw.get("name"), "Name"),
            email=require_email(raw.get("email")),
            active=bool(raw.get("active", True)),
        )


@dataclass
class Loan:
    loan_id: str
    isbn: str
    member_id: str
    issued: date
    due: date
    returned: date | None = None

    @property
    def is_active(self) -> bool:
        return self.returned is None

    def days_overdue(self, as_of: date) -> int:
        """Days past the due date, ignoring the grace period. Never negative."""
        if not self.is_active:
            return 0
        return max(0, (as_of - self.due).days)

    def fine(self, as_of: date) -> float:
        """Chargeable fine in pounds, applying the grace period."""
        chargeable_days = self.days_overdue(as_of) - GRACE_DAYS
        if chargeable_days <= 0:
            return 0.0
        return round(chargeable_days * FINE_PER_DAY, 2)

    def status(self, as_of: date) -> str:
        if not self.is_active:
            return "Returned"
        return "Overdue" if self.days_overdue(as_of) > 0 else "On loan"

    def to_dict(self) -> dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "isbn": self.isbn,
            "member_id": self.member_id,
            "issued": self.issued.isoformat(),
            "due": self.due.isoformat(),
            "returned": self.returned.isoformat() if self.returned else None,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Loan":
        issued = parse_date(raw.get("issued"), "Issued date")
        due = parse_date(raw.get("due"), "Due date")
        returned = _parse_optional_date(raw.get("returned"), "Returned date")
        if due < issued:
            raise ValidationError("Due date cannot be before the issue date.")
        if returned is not None and returned < issued:
            raise ValidationError("Returned date cannot be before the issue date.")
        return cls(
            loan_id=require_text(raw.get("loan_id"), "Loan ID", 20).upper(),
            isbn=normalise_isbn(raw.get("isbn")),
            member_id=require_text(raw.get("member_id"), "Member ID", 20).upper(),
            issued=issued,
            due=due,
            returned=returned,
        )

    def renew(self, days: int = LOAN_PERIOD_DAYS) -> None:
        self.due = self.due + timedelta(days=days)


# The loan period is derived, never stored twice: the due date is the truth.
def default_due_date(issued: date, days: int = LOAN_PERIOD_DAYS) -> date:
    return issued + timedelta(days=days)
