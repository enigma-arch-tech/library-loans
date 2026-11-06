# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Read-only reports and sorting.

These functions take a ``Library`` and return plain data (lists of rows,
dicts, strings) so the same report can be rendered by the CLI or the GUI.
"""

from __future__ import annotations

import heapq
from datetime import date, timedelta
from typing import Iterable

from .library import Library
from .models import (
    FINE_PER_DAY,
    GRACE_DAYS,
    LOAN_PERIOD_DAYS,
    MAX_ACTIVE_LOANS,
    Book,
    Loan,
)

SORT_OPTIONS = {
    "title": "Title (A-Z)",
    "author": "Author (A-Z)",
    "isbn": "ISBN",
    "year": "Year (newest first)",
    "status": "Availability",
    "due": "Due date (soonest first)",
}


def _due_date_for(library: Library, book: Book) -> date | None:
    for loan in library.loans:
        if loan.isbn == book.isbn and loan.is_active:
            return loan.due
    return None


def sort_books(
    library: Library,
    books: Iterable[Book],
    key: str = "title",
    reverse: bool = False,
) -> list[Book]:
    """Sort books with a stable, case-insensitive key.

    ``sorted`` uses Timsort, which is O(n log n) and stable, so equal keys keep
    their previous order (e.g. sorting by availability then title).
    """
    key = key if key in SORT_OPTIONS else "title"
    items = list(books)

    if key == "title":
        return sorted(items, key=lambda b: b.title.casefold(), reverse=reverse)
    if key == "author":
        return sorted(
            items, key=lambda b: (b.author.casefold(), b.title.casefold()), reverse=reverse
        )
    if key == "isbn":
        return sorted(items, key=lambda b: b.isbn, reverse=reverse)
    if key == "year":
        return sorted(
            items,
            key=lambda b: (b.year is None, -(b.year or 0), b.title.casefold()),
            reverse=reverse,
        )
    if key == "status":
        return sorted(
            items, key=lambda b: (b.on_loan, b.title.casefold()), reverse=reverse
        )
    if key == "due":
        return sorted(
            items,
            key=lambda b: (
                _due_date_for(library, b) is None,
                _due_date_for(library, b) or date.max,
                b.title.casefold(),
            ),
            reverse=reverse,
        )
    return items


def overdue_loans(library: Library, as_of: date | None = None) -> list[Loan]:
    """Active loans past their due date, most overdue first."""
    today = as_of or date.today()
    loans = [loan for loan in library.active_loans() if loan.due < today]
    return sorted(loans, key=lambda loan: (loan.due, loan.loan_id))


def loans_due_soon(
    library: Library, days: int = 7, as_of: date | None = None
) -> list[Loan]:
    """Active loans due within ``days``, soonest first.

    Uses ``heapq.nsmallest``: O(n log k) instead of sorting the whole list when
    only a few results are needed.
    """
    today = as_of or date.today()
    horizon = today + timedelta(days=days)
    candidates = [
        loan for loan in library.active_loans() if today <= loan.due <= horizon
    ]
    return heapq.nsmallest(len(candidates), candidates, key=lambda loan: (loan.due, loan.loan_id))


def member_history(library: Library, member_id: str) -> list[Loan]:
    """Every loan for one member, newest first."""
    member = library.get_member(member_id)
    loans = [loan for loan in library.loans if loan.member_id == member.member_id]
    return sorted(loans, key=lambda loan: (loan.issued, loan.loan_id), reverse=True)


def most_borrowed(library: Library, limit: int = 5) -> list[tuple[Book, int]]:
    """Books ranked by number of loans ever taken out."""
    counts: dict[str, int] = {}
    for loan in library.loans:
        counts[loan.isbn] = counts.get(loan.isbn, 0) + 1
    ranked = sorted(
        ((library.books[isbn], count) for isbn, count in counts.items() if isbn in library.books),
        key=lambda pair: (-pair[1], pair[0].title.casefold()),
    )
    return ranked[:limit]


def availability_summary(library: Library) -> dict[str, int]:
    total = len(library.books)
    on_loan = sum(1 for book in library.books.values() if book.on_loan)
    return {
        "titles": total,
        "on_loan": on_loan,
        "available": total - on_loan,
        "members": len(library.members),
        "active_members": sum(1 for member in library.members.values() if member.active),
        "active_loans": len(library.active_loans()),
        "loan_history": len(library.loans),
    }


def policy_summary() -> str:
    """Human-readable statement of the rules the app enforces."""
    return (
        f"Loan period: {LOAN_PERIOD_DAYS} days per loan. "
        f"Renewals: one per loan, +{LOAN_PERIOD_DAYS} days, only while not overdue. "
        f"Maximum concurrent loans per member: {MAX_ACTIVE_LOANS}. "
        f"Fines: GBP {FINE_PER_DAY:.2f} per day after a {GRACE_DAYS}-day grace period."
    )
