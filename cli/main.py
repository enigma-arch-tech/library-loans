# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Text-based (command-line) front end.

Run from the project root:

    python -m cli.main
    python -m cli.main --data data/library.json
    python -m cli.main --demo

The module contains presentation only; every rule lives in ``core``.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # allow "python cli/main.py" as well as "-m"
    sys.path.insert(0, str(ROOT))

from core import reports  # noqa: E402
from core.library import Library  # noqa: E402
from core.models import (  # noqa: E402
    LOAN_PERIOD_DAYS,
    MAX_ACTIVE_LOANS,
    LibraryError,
    parse_date,
)
from core.storage import StorageError  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "library.json"
SAMPLE_DATA = ROOT / "data" / "sample_library.json"

LINE = "=" * 78


class Cancelled(Exception):
    """The user pressed Enter at a required prompt or typed 'q'."""


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value if value else default


def ask_required(prompt: str) -> str:
    value = ask(prompt)
    if not value or value.lower() == "q":
        raise Cancelled
    return value


def ask_date(prompt: str, default: date | None = None, optional: bool = False) -> date | None:
    default_text = default.isoformat() if default else ""
    while True:
        raw = ask(prompt, default_text)
        if not raw:
            if optional:
                return None
            print("  A date is required (YYYY-MM-DD).")
            continue
        if raw.lower() == "q":
            raise Cancelled
        try:
            return parse_date(raw)
        except LibraryError as exc:
            print(f"  {exc}")


def ask_menu(title: str, options: dict[str, str]) -> str:
    """Print a numbered menu and return the chosen key."""
    print()
    print(title)
    print("-" * len(title))
    for key, label in options.items():
        print(f"  {key}) {label}")
    while True:
        choice = ask("Choose").lower()
        if choice in options:
            return choice
        print("  Not an option; try again.")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def render_table(headers: list[str], rows: list[list[object]]) -> str:
    cells = [[str(cell) for cell in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in cells:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    header_line = "  ".join(header.ljust(width) for header, width in zip(headers, widths))
    rule = "  ".join("-" * width for width in widths)
    body = "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)) for row in cells
    )
    return "\n".join(part for part in (header_line, rule, body) if part)


def print_books(library: Library, books) -> None:
    rows = [
        [book.isbn, book.title, book.author, book.year or "-", book.status]
        for book in books
    ]
    if not rows:
        print("  (no books to show)")
        return
    print(render_table(["ISBN", "Title", "Author", "Year", "Status"], rows))


def print_members(library: Library, members) -> None:
    rows = []
    for member in members:
        active = len(library.active_loans_for_member(member.member_id))
        rows.append([member.member_id, member.name, member.email, member.status, active])
    if not rows:
        print("  (no members to show)")
        return
    print(render_table(["ID", "Name", "Email", "Status", "On loan"], rows))


def print_loans(library: Library, loans, show_returned: bool = False) -> None:
    today = date.today()
    rows = []
    for loan in loans:
        book = library.books.get(loan.isbn)
        member = library.members.get(loan.member_id)
        rows.append(
            [
                loan.loan_id,
                book.title if book else loan.isbn,
                f"{loan.member_id} {member.name if member else ''}".strip(),
                loan.due.isoformat(),
                loan.status(today),
                f"{loan.fine(today):.2f}" if loan.is_active else "-",
            ]
        )
    if not rows:
        print("  (no loans to show)")
        return
    print(
        render_table(
            ["Loan", "Title", "Member", "Due", "Status", "Fine (GBP)"], rows
        )
    )


# ---------------------------------------------------------------------------
# Catalogue flows
# ---------------------------------------------------------------------------


def books_menu(library: Library, data_path: Path) -> None:
    while True:
        try:
            choice = ask_menu(
                "BOOKS",
                {
                    "1": "List all books",
                    "2": "Add a book",
                    "3": "Edit a book",
                    "4": "Remove a book",
                    "0": "Back",
                },
            )
        except (Cancelled, EOFError):
            return
        try:
            if choice == "1":
                print_books(library, reports.sort_books(library, library.all_books(), "title"))
            elif choice == "2":
                add_book_flow(library)
            elif choice == "3":
                edit_book_flow(library)
            elif choice == "4":
                remove_book_flow(library)
            else:
                save(library, data_path)
                return
        except Cancelled:
            print("  Cancelled.")
        except LibraryError as exc:
            print(f"  Error: {exc}")
        save(library, data_path)


def add_book_flow(library: Library) -> None:
    print("\nNew book (Enter 'q' at any prompt to cancel)")
    isbn = ask_required("ISBN")
    title = ask_required("Title")
    author = ask_required("Author")
    year = ask("Year (optional)")
    book = library.add_book(isbn, title, author, year or None)
    print(f"  Added: {book.title} ({book.isbn}).")


def choose_book(library: Library):
    isbn = ask_required("ISBN")
    return library.get_book(isbn)


def edit_book_flow(library: Library) -> None:
    book = choose_book(library)
    print(f"Editing '{book.title}'. Leave a field blank to keep the current value.")
    title = ask("Title", book.title)
    author = ask("Author", book.author)
    year = ask("Year", str(book.year) if book.year else "")
    library.update_book(book.isbn, title=title, author=author, year=year or None)
    print("  Saved.")


def remove_book_flow(library: Library) -> None:
    book = choose_book(library)
    if ask(f"Remove '{book.title}'? (y/N)").lower() != "y":
        print("  Cancelled.")
        return
    library.remove_book(book.isbn)
    print("  Removed.")


# ---------------------------------------------------------------------------
# Membership flows
# ---------------------------------------------------------------------------


def members_menu(library: Library, data_path: Path) -> None:
    while True:
        try:
            choice = ask_menu(
                "MEMBERS",
                {
                    "1": "List all members",
                    "2": "Add a member",
                    "3": "Edit a member",
                    "4": "Deactivate / reactivate",
                    "5": "Remove a member",
                    "0": "Back",
                },
            )
        except (Cancelled, EOFError):
            return
        try:
            if choice == "1":
                print_members(
                    library,
                    sorted(library.all_members(), key=lambda m: m.member_id),
                )
            elif choice == "2":
                name = ask_required("Name")
                email = ask_required("Email")
                member_id = ask("Member ID (blank to auto-generate)")
                member = library.add_member(name, email, member_id or None)
                print(f"  Added {member.member_id} ({member.name}).")
            elif choice == "3":
                member = library.get_member(ask_required("Member ID"))
                name = ask("Name", member.name)
                email = ask("Email", member.email)
                library.update_member(member.member_id, name=name, email=email)
                print("  Saved.")
            elif choice == "4":
                member = library.get_member(ask_required("Member ID"))
                library.update_member(member.member_id, active=not member.active)
                print(f"  {member.name} is now {member.status.lower()}.")
            elif choice == "5":
                member = library.get_member(ask_required("Member ID"))
                if ask(f"Remove {member.member_id}? (y/N)").lower() != "y":
                    print("  Cancelled.")
                else:
                    library.remove_member(member.member_id)
                    print("  Removed.")
            else:
                save(library, data_path)
                return
        except Cancelled:
            print("  Cancelled.")
        except LibraryError as exc:
            print(f"  Error: {exc}")
        save(library, data_path)


# ---------------------------------------------------------------------------
# Loan flows
# ---------------------------------------------------------------------------


def loans_menu(library: Library, data_path: Path) -> None:
    while True:
        try:
            choice = ask_menu(
                "LOANS",
                {
                    "1": "List active loans",
                    "2": "Issue a loan",
                    "3": "Return a book",
                    "4": "Renew a loan",
                    "5": "Full loan history",
                    "0": "Back",
                },
            )
        except (Cancelled, EOFError):
            return
        try:
            if choice == "1":
                print_loans(library, library.active_loans())
            elif choice == "2":
                isbn = ask_required("ISBN")
                member_id = ask_required("Member ID")
                loan = library.issue_loan(isbn, member_id)
                print(
                    f"  Issued {loan.loan_id}: due {loan.due.isoformat()} "
                    f"({LOAN_PERIOD_DAYS} days)."
                )
            elif choice == "3":
                isbn = ask_required("ISBN")
                loan = library.return_loan(isbn)
                fine = loan.fine(date.today())
                print(f"  {loan.loan_id} returned.")
                if fine:
                    print(f"  Fine due: GBP {fine:.2f}")
            elif choice == "4":
                isbn = ask_required("ISBN")
                loan = library.renew_loan(isbn)
                print(f"  Renewed; new due date {loan.due.isoformat()}.")
            elif choice == "5":
                print_loans(library, library.loans)
            else:
                save(library, data_path)
                return
        except Cancelled:
            print("  Cancelled.")
        except LibraryError as exc:
            print(f"  Error: {exc}")
        save(library, data_path)


# ---------------------------------------------------------------------------
# Search and reports
# ---------------------------------------------------------------------------


def search_menu(library: Library) -> None:
    while True:
        try:
            choice = ask_menu(
                "SEARCH AND SORT",
                {
                    "1": "Search by title, author or ISBN",
                    "2": "Sort the catalogue",
                    "0": "Back",
                },
            )
        except (Cancelled, EOFError):
            return
        try:
            if choice == "1":
                query = ask_required("Search text")
                results = library.search_books(query)
                print(f"  {len(results)} match(es) for '{query}'.")
                print_books(library, results)
            elif choice == "2":
                options = {str(index): label for index, label in enumerate(
                    reports.SORT_OPTIONS.values(), start=1)}
                keys = list(reports.SORT_OPTIONS)
                chosen = ask_menu("SORT BY", options)
                books = reports.sort_books(library, library.all_books(), keys[int(chosen) - 1])
                print_books(library, books)
            else:
                return
        except Cancelled:
            print("  Cancelled.")
        except LibraryError as exc:
            print(f"  Error: {exc}")


def reports_menu(library: Library) -> None:
    while True:
        try:
            choice = ask_menu(
                "REPORTS",
                {
                    "1": "Availability summary",
                    "2": "Overdue loans and fines",
                    "3": "Loans due in the next 7 days",
                    "4": "Most borrowed titles",
                    "5": "Member loan history",
                    "6": "Loan policy",
                    "0": "Back",
                },
            )
        except (Cancelled, EOFError):
            return
        try:
            if choice == "1":
                summary = reports.availability_summary(library)
                print()
                for label, key in [
                    ("Titles", "titles"),
                    ("On loan", "on_loan"),
                    ("Available", "available"),
                    ("Members", "members"),
                    ("Active members", "active_members"),
                    ("Active loans", "active_loans"),
                    ("Loan records", "loan_history"),
                ]:
                    print(f"  {label:<16}{summary[key]:>6}")
            elif choice == "2":
                loans = reports.overdue_loans(library)
                print(f"  {len(loans)} overdue loan(s).")
                print_loans(library, loans)
            elif choice == "3":
                print_loans(library, reports.loans_due_soon(library, 7))
            elif choice == "4":
                for book, count in reports.most_borrowed(library, 5):
                    print(f"  {count:>3}x  {book.title} — {book.author}")
            elif choice == "5":
                member = library.get_member(ask_required("Member ID"))
                print(f"\n  History for {member.name} ({member.member_id})")
                print_loans(library, reports.member_history(library, member.member_id))
            elif choice == "6":
                print(f"\n  {reports.policy_summary()}")
            else:
                return
        except Cancelled:
            print("  Cancelled.")
        except LibraryError as exc:
            print(f"  Error: {exc}")


# ---------------------------------------------------------------------------
# Application entry points
# ---------------------------------------------------------------------------


def save(library: Library, path: Path) -> None:
    try:
        library.save(path)
    except StorageError as exc:
        print(f"  Could not save: {exc}")


def load_library(data_path: Path) -> Library:
    try:
        return Library.load_or_seed(data_path, SAMPLE_DATA)
    except (StorageError, LibraryError) as exc:
        print(f"Could not load the library: {exc}")
        raise SystemExit(1)


def run_demo(library: Library) -> None:
    """Scripted walkthrough used when recording the demonstration video."""
    today = date.today()
    print(LINE)
    print("DEMO: requirements walkthrough (changes are not saved)")
    print(LINE)

    print("\n[FR1/FR7] Catalogue and search")
    print_books(library, reports.sort_books(library, library.search_books("java"), "title"))

    print("\n[FR4/FR5] Issue and return")
    loan = library.issue_loan("9780262033848", "M0002")
    print(f"  Issued {loan.loan_id} to M0002, due {loan.due.isoformat()}")
    ended = library.return_loan("9780262033848", today)
    print(f"  Returned on {ended.returned.isoformat()}")

    print("\n[FR9] Overdue report with fines")
    old = library.issue_loan("9780132350884", "M0001", today - timedelta(days=25))
    print(f"  Loan {old.loan_id} backdated; due {old.due.isoformat()}")
    print_loans(library, reports.overdue_loans(library))
    print(f"  Calculated fine: GBP {old.fine(today):.2f}")

    print("\n[FR11] Most borrowed")
    for book, count in reports.most_borrowed(library, 5):
        print(f"  {count:>3}x  {book.title}")

    print("\n[FR12] Availability summary")
    summary = reports.availability_summary(library)
    print(
        f"  {summary['titles']} titles, {summary['available']} available, "
        f"{summary['on_loan']} on loan, {summary['members']} members"
    )

    print("\n[FR6] Renewal")
    renewal = library.issue_loan("9780596007126", "M0003")
    before = renewal.due
    library.renew_loan(renewal.isbn)
    print(f"  Due {before.isoformat()} -> {renewal.due.isoformat()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Library Loans Manager (text interface)")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="path to the JSON data file")
    parser.add_argument("--demo", action="store_true", help="run a scripted demonstration")
    args = parser.parse_args(argv)

    library = load_library(args.data)
    if args.demo:
        run_demo(library)
        return 0

    print(LINE)
    print("LIBRARY LOANS MANAGER — text interface")
    print(f"Data file: {args.data}")
    print(LINE)

    try:
        while True:
            choice = ask_menu(
                "MAIN MENU",
                {
                    "1": "Books",
                    "2": "Members",
                    "3": "Loans",
                    "4": "Search and sort",
                    "5": "Reports",
                    "6": "Save now",
                    "0": "Exit",
                },
            )
            if choice == "1":
                books_menu(library, args.data)
            elif choice == "2":
                members_menu(library, args.data)
            elif choice == "3":
                loans_menu(library, args.data)
            elif choice == "4":
                search_menu(library)
            elif choice == "5":
                reports_menu(library)
            elif choice == "6":
                save(library, args.data)
                print("  Saved.")
            else:
                break
    except (KeyboardInterrupt, EOFError):
        print("\nInterrupted.")
    finally:
        save(library, args.data)
        print("Library saved. Goodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
