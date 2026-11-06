# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""The in-memory aggregate: catalogue, membership and loans.

Data structures
---------------
* ``books``   : ``dict[str, Book]`` keyed by ISBN  -> O(1) lookup/uniqueness.
* ``members`` : ``dict[str, Member]`` keyed by ID -> O(1) lookup/uniqueness.
* ``loans``   : ``list[Loan]`` append-only history; the current state of a book
  is derived from it, so the two can never drift apart.
* ``_index``  : word -> set of ISBNs, maintained on every catalogue change, used
  to narrow searches before the substring filter runs.

All mutations raise ``LibraryError`` subclasses; nothing here prints.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterable

from .models import (
    MAX_ACTIVE_LOANS,
    Book,
    DuplicateError,
    Loan,
    LoanError,
    Member,
    NotFoundError,
    ValidationError,
    default_due_date,
    normalise_isbn,
    parse_date,
    require_email,
    require_text,
    require_year,
)
from .storage import SCHEMA_VERSION, StorageError, ensure_data_file, load_json, save_json

DEFAULT_DATA_PATH = Path("data") / "library.json"
SAMPLE_DATA_PATH = Path("data") / "sample_library.json"

_TOKEN_SPLIT = re.compile(r"[^0-9a-z]+")


class _UnsetType:
    """Sentinel so that 'leave unchanged' and 'set to empty' are different."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<unset>"


UNSET = _UnsetType()


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_SPLIT.split(text.casefold()) if token}


class Library:
    """Owns all records and enforces every business rule."""

    def __init__(self) -> None:
        self.books: dict[str, Book] = {}
        self.members: dict[str, Member] = {}
        self.loans: list[Loan] = []
        self._index: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Catalogue
    # ------------------------------------------------------------------

    def add_book(
        self,
        isbn: str,
        title: str,
        author: str,
        year: int | str | None = None,
    ) -> Book:
        key = normalise_isbn(isbn)
        if key in self.books:
            raise DuplicateError(f"A book with ISBN {key} already exists.")
        book = Book(
            isbn=key,
            title=require_text(title, "Title"),
            author=require_text(author, "Author"),
            year=require_year(year),
        )
        self.books[key] = book
        self._index_book(book)
        return book

    def update_book(
        self,
        isbn: str,
        *,
        title: str | None = None,
        author: str | None = None,
        year: int | str | None | _UnsetType = UNSET,
    ) -> Book:
        book = self.get_book(isbn)
        self._unindex_book(book)
        if title is not None:
            book.title = require_text(title, "Title")
        if author is not None:
            book.author = require_text(author, "Author")
        if year is not UNSET:
            book.year = require_year(year)
        self._index_book(book)
        return book

    def remove_book(self, isbn: str) -> Book:
        book = self.get_book(isbn)
        if book.on_loan:
            raise LoanError(f"'{book.title}' is on loan and cannot be removed.")
        if any(loan.isbn == book.isbn for loan in self.loans):
            raise LoanError(
                f"'{book.title}' has loan history and cannot be removed; "
                "keep it for the audit trail."
            )
        self._unindex_book(book)
        del self.books[book.isbn]
        return book

    def get_book(self, isbn: str) -> Book:
        key = normalise_isbn(isbn)
        try:
            return self.books[key]
        except KeyError:
            raise NotFoundError(f"No book found with ISBN {key}.") from None

    def all_books(self) -> Iterable[Book]:
        return self.books.values()

    # ------------------------------------------------------------------
    # Membership
    # ------------------------------------------------------------------

    def add_member(
        self,
        name: str,
        email: str,
        member_id: str | None = None,
    ) -> Member:
        clean_name = require_text(name, "Name")
        clean_email = require_email(email)
        key = (member_id or self.next_member_id()).strip().upper()
        if not key:
            raise ValidationError("Member ID is required.")
        if key in self.members:
            raise DuplicateError(f"Member ID {key} already exists.")
        if any(m.email.casefold() == clean_email.casefold() for m in self.members.values()):
            raise DuplicateError(f"A member with email {clean_email} already exists.")
        member = Member(member_id=key, name=clean_name, email=clean_email)
        self.members[key] = member
        return member

    def update_member(
        self,
        member_id: str,
        *,
        name: str | None = None,
        email: str | None = None,
        active: bool | None = None,
    ) -> Member:
        member = self.get_member(member_id)
        if name is not None:
            member.name = require_text(name, "Name")
        if email is not None:
            clean_email = require_email(email)
            for other in self.members.values():
                if other is not member and other.email.casefold() == clean_email.casefold():
                    raise DuplicateError(f"A member with email {clean_email} already exists.")
            member.email = clean_email
        if active is not None:
            member.active = bool(active)
        return member

    def remove_member(self, member_id: str) -> Member:
        member = self.get_member(member_id)
        if any(loan.member_id == member.member_id for loan in self.loans):
            raise LoanError(
                f"{member.name} has loan history and cannot be removed; "
                "mark the membership inactive instead."
            )
        del self.members[member.member_id]
        return member

    def get_member(self, member_id: str) -> Member:
        key = str(member_id).strip().upper()
        try:
            return self.members[key]
        except KeyError:
            raise NotFoundError(f"No member found with ID {key}.") from None

    def all_members(self) -> Iterable[Member]:
        return self.members.values()

    def next_member_id(self) -> str:
        numbers = [0]
        for key in self.members:
            if key.startswith("M") and key[1:].isdigit():
                numbers.append(int(key[1:]))
        return f"M{max(numbers) + 1:04d}"

    # ------------------------------------------------------------------
    # Loans
    # ------------------------------------------------------------------

    def issue_loan(
        self,
        isbn: str,
        member_id: str,
        issued: date | str | None = None,
    ) -> Loan:
        book = self.get_book(isbn)
        member = self.get_member(member_id)
        if not member.active:
            raise LoanError(f"{member.name} is inactive and cannot borrow.")
        if book.on_loan:
            raise LoanError(f"'{book.title}' is already on loan.")
        issued_on = parse_date(issued, "Issue date") if issued else date.today()
        if issued_on > date.today():
            raise ValidationError("Issue date cannot be in the future.")
        if len(self.active_loans_for_member(member.member_id)) >= MAX_ACTIVE_LOANS:
            raise LoanError(
                f"{member.name} already has {MAX_ACTIVE_LOANS} loans, the maximum allowed."
            )
        loan = Loan(
            loan_id=self.next_loan_id(),
            isbn=book.isbn,
            member_id=member.member_id,
            issued=issued_on,
            due=default_due_date(issued_on),
        )
        self.loans.append(loan)
        book.on_loan = True
        return loan

    def return_loan(self, isbn: str, returned: date | str | None = None) -> Loan:
        book = self.get_book(isbn)
        loan = self.active_loan_for(book.isbn)
        returned_on = parse_date(returned, "Return date") if returned else date.today()
        if returned_on < loan.issued:
            raise ValidationError("Return date cannot be before the issue date.")
        loan.returned = returned_on
        book.on_loan = False
        return loan

    def renew_loan(self, isbn: str, as_of: date | None = None) -> Loan:
        book = self.get_book(isbn)
        loan = self.active_loan_for(book.isbn)
        today = as_of or date.today()
        if loan.due < today:
            raise LoanError(
                f"'{book.title}' is overdue; it must be returned before it can be renewed."
            )
        loan.renew()
        return loan

    def active_loan_for(self, isbn: str) -> Loan:
        key = normalise_isbn(isbn)
        for loan in self.loans:
            if loan.isbn == key and loan.is_active:
                return loan
        raise LoanError(f"No active loan found for ISBN {key}.")

    def active_loans(self) -> list[Loan]:
        return [loan for loan in self.loans if loan.is_active]

    def active_loans_for_member(self, member_id: str) -> list[Loan]:
        key = str(member_id).strip().upper()
        return [loan for loan in self.loans if loan.is_active and loan.member_id == key]

    def next_loan_id(self) -> str:
        numbers = [0]
        for loan in self.loans:
            if loan.loan_id.startswith("L") and loan.loan_id[1:].isdigit():
                numbers.append(int(loan.loan_id[1:]))
        return f"L{max(numbers) + 1:04d}"

    # ------------------------------------------------------------------
    # Search and sort
    # ------------------------------------------------------------------

    def search_books(self, query: str) -> list[Book]:
        """Case-insensitive substring search over title, author and ISBN.

        The word index is used as a fast path when the query is one whole word
        already present in it; the substring test is always applied afterwards,
        so results stay correct for partial words.
        """
        text = str(query or "").strip().casefold()
        if not text:
            return sorted(self.books.values(), key=lambda book: book.title.casefold())
        if " " not in text and text in self._index:
            candidates = (self.books[isbn] for isbn in self._index[text] if isbn in self.books)
        else:
            candidates = self.books.values()
        return sorted(
            (
                book
                for book in candidates
                if text in book.title.casefold()
                or text in book.author.casefold()
                or text in book.isbn.casefold()
            ),
            key=lambda book: (book.title.casefold(), book.author.casefold()),
        )

    def _index_book(self, book: Book) -> None:
        for token in _tokens(f"{book.title} {book.author}"):
            self._index.setdefault(token, set()).add(book.isbn)

    def _unindex_book(self, book: Book) -> None:
        for token in _tokens(f"{book.title} {book.author}"):
            bucket = self._index.get(token)
            if bucket is not None:
                bucket.discard(book.isbn)
                if not bucket:
                    del self._index[token]

    def _rebuild_index(self) -> None:
        self._index = {}
        for book in self.books.values():
            self._index_book(book)

    def borrowing_counts(self) -> Counter[str]:
        """Number of loans ever taken out, per member."""
        return Counter(loan.member_id for loan in self.loans)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "books": [book.to_dict() for book in sorted(self.books.values(), key=lambda b: b.isbn)],
            "members": [
                member.to_dict()
                for member in sorted(self.members.values(), key=lambda m: m.member_id)
            ],
            "loans": [loan.to_dict() for loan in self.loans],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Library":
        library = cls()
        for item in raw.get("books", []):
            book = Book.from_dict(item)
            if book.isbn in library.books:
                raise ValidationError(f"Duplicate ISBN {book.isbn} in data file.")
            library.books[book.isbn] = book
        for item in raw.get("members", []):
            member = Member.from_dict(item)
            if member.member_id in library.members:
                raise ValidationError(f"Duplicate member ID {member.member_id} in data file.")
            library.members[member.member_id] = member
        for item in raw.get("loans", []):
            loan = Loan.from_dict(item)
            if loan.isbn not in library.books:
                raise ValidationError(f"Loan {loan.loan_id} refers to unknown ISBN {loan.isbn}.")
            if loan.member_id not in library.members:
                raise ValidationError(
                    f"Loan {loan.loan_id} refers to unknown member {loan.member_id}."
                )
            library.loans.append(loan)

        # Derive availability from history so the two cannot contradict.
        for book in library.books.values():
            book.on_loan = False
        for loan in library.loans:
            if loan.is_active:
                library.books[loan.isbn].on_loan = True
        library._rebuild_index()
        return library

    def save(self, path: str | Path = DEFAULT_DATA_PATH) -> None:
        save_json(path, self.to_dict())

    @classmethod
    def load(cls, path: str | Path = DEFAULT_DATA_PATH) -> "Library":
        try:
            return cls.from_dict(load_json(path))
        except StorageError:
            raise
        except ValidationError as exc:
            raise StorageError(f"Data file is inconsistent: {exc}") from None

    @classmethod
    def load_or_seed(
        cls,
        path: str | Path = DEFAULT_DATA_PATH,
        sample_path: str | Path = SAMPLE_DATA_PATH,
    ) -> "Library":
        """Load the working file, creating it from the sample on first run."""
        ensure_data_file(path, sample_path)
        return cls.load(path)
