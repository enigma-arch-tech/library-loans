# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Tkinter front end for the Library Loans Manager.

Run from the project root:

    python -m gui.app
    python gui/app.py --data data/library.json

The window is a ``ttk.Notebook`` with one tab per area. Every mutating action
calls a ``core`` method and then ``LibraryApp.after_change`` which saves the
data file and refreshes the visible tables. No business rule is duplicated here.
"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import reports  # noqa: E402
from core.library import Library  # noqa: E402
from core.models import LOAN_PERIOD_DAYS, LibraryError  # noqa: E402
from core.storage import StorageError  # noqa: E402

DEFAULT_DATA = ROOT / "data" / "library.json"
SAMPLE_DATA = ROOT / "data" / "sample_library.json"


# ---------------------------------------------------------------------------
# Reusable modal form
# ---------------------------------------------------------------------------


class FormDialog(tk.Toplevel):
    """A modal form built from a list of field definitions.

    ``fields`` is a list of dicts with the keys ``key``, ``label``, ``default``,
    and the optional keys ``optional`` and ``readonly``. ``FormDialog.ask``
    returns a dict of strings, or ``None`` when cancelled.
    """

    def __init__(self, master: tk.Misc, title: str, fields: list[dict[str, Any]], hint: str = ""):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self._vars: dict[str, tk.StringVar] = {}

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        if hint:
            ttk.Label(body, text=hint, foreground="#555").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
            )
        first_entry: ttk.Entry | None = None
        for index, field in enumerate(fields, start=1):
            marker = "" if field.get("optional") else " *"
            ttk.Label(body, text=f"{field['label']}{marker}").grid(
                row=index, column=0, sticky="w", padx=(0, 12), pady=4
            )
            var = tk.StringVar(value=str(field.get("default", "")))
            self._vars[field["key"]] = var
            entry = ttk.Entry(body, textvariable=var, width=42)
            entry.grid(row=index, column=1, sticky="we", pady=4)
            if field.get("readonly"):
                entry.state(["readonly"])
            elif first_entry is None:
                first_entry = entry

        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="right")

        self.bind("<Return>", lambda _event: self._ok())
        self.bind("<Escape>", lambda _event: self._cancel())
        self.transient(master)
        self.grab_set()
        self.update_idletasks()
        self._centre_on(master)
        if first_entry is not None:
            first_entry.focus_set()
        self.wait_window(self)

    def _centre_on(self, master: tk.Misc) -> None:
        width, height = self.winfo_width(), self.winfo_height()
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - height) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _ok(self) -> None:
        self.result = {key: var.get().strip() for key, var in self._vars.items()}
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    @staticmethod
    def ask(
        master: tk.Misc, title: str, fields: list[dict[str, Any]], hint: str = ""
    ) -> dict[str, str] | None:
        return FormDialog(master, title, fields, hint).result


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


class BooksTab(ttk.Frame):
    def __init__(self, master: tk.Misc, app: "LibraryApp"):
        super().__init__(master, padding=8)
        self.app = app
        self.sort_key = "title"

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))

        ttk.Label(toolbar, text="Search").pack(side="left")
        self.query = tk.StringVar()
        search = ttk.Entry(toolbar, textvariable=self.query, width=26)
        search.pack(side="left", padx=4)
        search.bind("<Return>", lambda _event: self.refresh())
        ttk.Button(toolbar, text="Search", command=self.refresh).pack(side="left")
        ttk.Button(toolbar, text="Clear", command=self.clear).pack(side="left", padx=4)

        ttk.Label(toolbar, text="Sort by").pack(side="left", padx=(14, 4))
        self.sort_box = ttk.Combobox(
            toolbar,
            state="readonly",
            width=24,
            values=list(reports.SORT_OPTIONS.values()),
        )
        self.sort_box.current(0)
        self.sort_box.pack(side="left")
        self.sort_box.bind("<<ComboboxSelected>>", self._on_sort)

        ttk.Button(toolbar, text="Remove", command=self.remove).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Edit", command=self.edit).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Add book", command=self.add).pack(side="right")

        columns = ("isbn", "title", "author", "year", "status")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for column, heading, width, anchor in [
            ("isbn", "ISBN", 130, "w"),
            ("title", "Title", 280, "w"),
            ("author", "Author", 190, "w"),
            ("year", "Year", 60, "center"),
            ("status", "Status", 90, "center"),
        ]:
            self.tree.heading(column, text=heading, command=lambda c=column: self._sort_by(c))
            self.tree.column(column, width=width, anchor=anchor, stretch=(column == "title"))
        self._add_scrollbar(self.tree)
        self.tree.bind("<Double-1>", lambda _event: self.edit())

        self.refresh()

    def _add_scrollbar(self, tree: ttk.Treeview) -> None:
        tree.pack(side="left", fill="both", expand=True)
        bar = ttk.Scrollbar(self, orient="vertical", command=tree.yview)
        bar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=bar.set)

    def _on_sort(self, _event: tk.Event) -> None:
        self.sort_key = list(reports.SORT_OPTIONS)[self.sort_box.current()]
        self.refresh()

    def _sort_by(self, column: str) -> None:
        mapping = {
            "isbn": "isbn",
            "title": "title",
            "author": "author",
            "year": "year",
            "status": "status",
        }
        key = mapping.get(column, "title")
        self.sort_key = key
        self.sort_box.current(list(reports.SORT_OPTIONS).index(key))
        self.refresh()

    def clear(self) -> None:
        self.query.set("")
        self.refresh()

    def refresh(self) -> None:
        text = self.query.get().strip()
        books = (
            self.app.library.search_books(text)
            if text
            else list(self.app.library.all_books())
        )
        books = reports.sort_books(self.app.library, books, self.sort_key)
        self.tree.delete(*self.tree.get_children())
        for book in books:
            self.tree.insert(
                "",
                "end",
                iid=book.isbn,
                values=(book.isbn, book.title, book.author, book.year or "-", book.status),
            )

    def _selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Select a book", "Choose a book in the list first.", parent=self)
            return None
        try:
            return self.app.library.get_book(selection[0])
        except LibraryError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return None

    def add(self) -> None:
        values = FormDialog.ask(
            self,
            "Add book",
            [
                {"key": "isbn", "label": "ISBN (10 or 13 digits)"},
                {"key": "title", "label": "Title"},
                {"key": "author", "label": "Author"},
                {"key": "year", "label": "Year", "optional": True},
            ],
            hint="The ISBN check digit is validated before the book is saved.",
        )
        if values is None:
            return
        try:
            book = self.app.library.add_book(
                values["isbn"], values["title"], values["author"], values["year"] or None
            )
        except LibraryError as exc:
            self._error(exc)
            return
        self.app.after_change(f"Added '{book.title}'.")

    def edit(self) -> None:
        book = self._selected()
        if book is None:
            return
        values = FormDialog.ask(
            self,
            "Edit book",
            [
                {"key": "isbn", "label": "ISBN", "default": book.isbn, "readonly": True},
                {"key": "title", "label": "Title", "default": book.title},
                {"key": "author", "label": "Author", "default": book.author},
                {"key": "year", "label": "Year", "default": book.year or "", "optional": True},
            ],
        )
        if values is None:
            return
        try:
            self.app.library.update_book(
                book.isbn,
                title=values["title"],
                author=values["author"],
                year=values["year"] or None,
            )
        except LibraryError as exc:
            self._error(exc)
            return
        self.app.after_change(f"Updated '{values['title']}'.")

    def remove(self) -> None:
        book = self._selected()
        if book is None:
            return
        if not messagebox.askyesno("Remove book", f"Remove '{book.title}'?", parent=self):
            return
        try:
            self.app.library.remove_book(book.isbn)
        except LibraryError as exc:
            self._error(exc)
            return
        self.app.after_change(f"Removed '{book.title}'.")

    def _error(self, exc: Exception) -> None:
        messagebox.showerror("Error", str(exc), parent=self)


class MembersTab(ttk.Frame):
    def __init__(self, master: tk.Misc, app: "LibraryApp"):
        super().__init__(master, padding=8)
        self.app = app

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Members are identified automatically; ids look like M0001.").pack(
            side="left"
        )
        ttk.Button(toolbar, text="Remove", command=self.remove).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Deactivate / activate", command=self.toggle).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(toolbar, text="Edit", command=self.edit).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Add member", command=self.add).pack(side="right")

        columns = ("id", "name", "email", "status", "loans")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for column, heading, width, anchor in [
            ("id", "Member ID", 100, "w"),
            ("name", "Name", 220, "w"),
            ("email", "Email", 240, "w"),
            ("status", "Status", 90, "center"),
            ("loans", "On loan", 80, "center"),
        ]:
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor=anchor, stretch=(column == "name"))
        self.tree.pack(side="left", fill="both", expand=True)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        bar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.bind("<Double-1>", lambda _event: self.edit())

        self.refresh()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for member in sorted(self.app.library.all_members(), key=lambda m: m.member_id):
            loans = len(self.app.library.active_loans_for_member(member.member_id))
            self.tree.insert(
                "",
                "end",
                iid=member.member_id,
                values=(member.member_id, member.name, member.email, member.status, loans),
            )

    def _selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Select a member", "Choose a member in the list first.", parent=self)
            return None
        try:
            return self.app.library.get_member(selection[0])
        except LibraryError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return None

    def add(self) -> None:
        values = FormDialog.ask(
            self,
            "Add member",
            [
                {"key": "name", "label": "Name"},
                {"key": "email", "label": "Email"},
                {"key": "member_id", "label": "Member ID", "optional": True},
            ],
            hint="Leave the member ID blank to generate the next one.",
        )
        if values is None:
            return
        try:
            member = self.app.library.add_member(
                values["name"], values["email"], values["member_id"] or None
            )
        except LibraryError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.app.after_change(f"Added {member.member_id} ({member.name}).")

    def edit(self) -> None:
        member = self._selected()
        if member is None:
            return
        values = FormDialog.ask(
            self,
            "Edit member",
            [
                {"key": "id", "label": "Member ID", "default": member.member_id, "readonly": True},
                {"key": "name", "label": "Name", "default": member.name},
                {"key": "email", "label": "Email", "default": member.email},
            ],
        )
        if values is None:
            return
        try:
            self.app.library.update_member(
                member.member_id, name=values["name"], email=values["email"]
            )
        except LibraryError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.app.after_change(f"Updated {member.member_id}.")

    def toggle(self) -> None:
        member = self._selected()
        if member is None:
            return
        try:
            self.app.library.update_member(member.member_id, active=not member.active)
        except LibraryError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.app.after_change(f"{member.name} is now {member.status.lower()}.")

    def remove(self) -> None:
        member = self._selected()
        if member is None:
            return
        if not messagebox.askyesno("Remove member", f"Remove {member.name}?", parent=self):
            return
        try:
            self.app.library.remove_member(member.member_id)
        except LibraryError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        self.app.after_change(f"Removed {member.name}.")


class LoansTab(ttk.Frame):
    def __init__(self, master: tk.Misc, app: "LibraryApp"):
        super().__init__(master, padding=8)
        self.app = app
        self.show_returned = tk.BooleanVar(value=False)

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(
            toolbar,
            text="Show returned loans",
            variable=self.show_returned,
            command=self.refresh,
        ).pack(side="left")
        ttk.Label(toolbar, text="Double-click a row to return it.").pack(side="left", padx=14)

        ttk.Button(toolbar, text="Renew", command=self.renew).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Return", command=self.return_book).pack(side="right", padx=(6, 0))
        ttk.Button(toolbar, text="Issue loan", command=self.issue).pack(side="right")

        columns = ("loan", "isbn", "title", "member", "due", "status", "fine")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for column, heading, width, anchor in [
            ("loan", "Loan", 70, "w"),
            ("isbn", "ISBN", 120, "w"),
            ("title", "Title", 240, "w"),
            ("member", "Member", 170, "w"),
            ("due", "Due", 95, "center"),
            ("status", "Status", 85, "center"),
            ("fine", "Fine (GBP)", 85, "e"),
        ]:
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor=anchor, stretch=(column == "title"))
        self.tree.pack(side="left", fill="both", expand=True)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        bar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.bind("<Double-1>", lambda _event: self.return_book())

        self.refresh()

    def refresh(self) -> None:
        today = date.today()
        library = self.app.library
        loans = library.loans if self.show_returned.get() else library.active_loans()
        self.tree.delete(*self.tree.get_children())
        for loan in sorted(loans, key=lambda item: (item.returned is not None, item.due)):
            book = library.books.get(loan.isbn)
            member = library.members.get(loan.member_id)
            title = book.title if book else loan.isbn
            person = f"{loan.member_id} {member.name if member else ''}".strip()
            fine = f"{loan.fine(today):.2f}" if loan.is_active else "-"
            self.tree.insert(
                "",
                "end",
                iid=loan.loan_id,
                values=(
                    loan.loan_id,
                    loan.isbn,
                    title,
                    person,
                    loan.due.isoformat(),
                    loan.status(today),
                    fine,
                ),
            )

    def _selected_loan(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Select a loan", "Choose a loan in the list first.", parent=self)
            return None
        loan_id = selection[0]
        for loan in self.app.library.loans:
            if loan.loan_id == loan_id:
                return loan
        return None

    def issue(self) -> None:
        values = FormDialog.ask(
            self,
            "Issue loan",
            [
                {"key": "isbn", "label": "Book ISBN"},
                {"key": "member_id", "label": "Member ID"},
                {
                    "key": "issued",
                    "label": "Issue date (YYYY-MM-DD)",
                    "default": date.today().isoformat(),
                },
            ],
            hint=f"The due date is {LOAN_PERIOD_DAYS} days after the issue date.",
        )
        if values is None:
            return
        try:
            loan = self.app.library.issue_loan(
                values["isbn"], values["member_id"], values["issued"]
            )
        except LibraryError as exc:
            messagebox.showerror("Cannot issue loan", str(exc), parent=self)
            return
        self.app.after_change(f"{loan.loan_id} issued, due {loan.due.isoformat()}.")

    def return_book(self) -> None:
        loan = self._selected_loan()
        if loan is None:
            return
        if not loan.is_active:
            messagebox.showinfo("Already returned", "That loan is already closed.", parent=self)
            return
        try:
            book = self.app.library.get_book(loan.isbn)
            closed = self.app.library.return_loan(loan.isbn)
        except LibraryError as exc:
            messagebox.showerror("Cannot return", str(exc), parent=self)
            return
        fine = closed.fine(date.today())
        message = f"'{book.title}' returned."
        if fine:
            message += f" Fine due: GBP {fine:.2f}."
        self.app.after_change(message)

    def renew(self) -> None:
        loan = self._selected_loan()
        if loan is None:
            return
        try:
            renewed = self.app.library.renew_loan(loan.isbn)
        except LibraryError as exc:
            messagebox.showerror("Cannot renew", str(exc), parent=self)
            return
        self.app.after_change(f"Renewed; new due date {renewed.due.isoformat()}.")


class ReportsTab(ttk.Frame):
    def __init__(self, master: tk.Misc, app: "LibraryApp"):
        super().__init__(master, padding=8)
        self.app = app

        sidebar = ttk.Frame(self)
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        for label, command in [
            ("Availability summary", self.show_availability),
            ("Overdue loans and fines", self.show_overdue),
            ("Due in the next 7 days", self.show_due_soon),
            ("Most borrowed titles", self.show_most_borrowed),
            ("Member loan history", self.show_member_history),
            ("Loan policy", self.show_policy),
        ]:
            ttk.Button(sidebar, text=label, width=26, command=command).pack(fill="x", pady=3)

        self.output = tk.Text(self, wrap="word", height=24, width=80, relief="solid", borderwidth=1)
        self.output.pack(side="left", fill="both", expand=True)
        self.output.configure(state="disabled")
        self.show_availability()

    def _write(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def refresh(self) -> None:
        self.show_availability()

    def show_availability(self) -> None:
        summary = reports.availability_summary(self.app.library)
        lines = ["Availability summary", "=" * 20]
        for label, key in [
            ("Titles", "titles"),
            ("On loan", "on_loan"),
            ("Available", "available"),
            ("Members", "members"),
            ("Active members", "active_members"),
            ("Active loans", "active_loans"),
            ("Loan records", "loan_history"),
        ]:
            lines.append(f"{label:<16}{summary[key]:>6}")
        self._write("\n".join(lines))

    def _loan_lines(self, loans) -> list[str]:
        today = date.today()
        library = self.app.library
        lines = [f"{'Loan':<7}{'Title':<38}{'Member':<20}{'Due':<12}{'Fine':>8}"]
        for loan in loans:
            book = library.books.get(loan.isbn)
            member = library.members.get(loan.member_id)
            title = (book.title if book else loan.isbn)[:36]
            person = f"{loan.member_id} {member.name if member else ''}"[:18]
            fine = f"{loan.fine(today):.2f}" if loan.is_active else "-"
            lines.append(
                f"{loan.loan_id:<7}{title:<38}{person:<20}{loan.due.isoformat():<12}{fine:>8}"
            )
        return lines

    def show_overdue(self) -> None:
        loans = reports.overdue_loans(self.app.library)
        lines = [f"Overdue loans ({len(loans)})", "=" * 20]
        lines.extend(self._loan_lines(loans) if loans else ["Nothing is overdue."])
        self._write("\n".join(lines))

    def show_due_soon(self) -> None:
        loans = reports.loans_due_soon(self.app.library, 7)
        lines = [f"Due in the next 7 days ({len(loans)})", "=" * 30]
        lines.extend(self._loan_lines(loans) if loans else ["Nothing is due this week."])
        self._write("\n".join(lines))

    def show_most_borrowed(self) -> None:
        lines = ["Most borrowed titles", "=" * 20]
        for book, count in reports.most_borrowed(self.app.library, 10):
            lines.append(f"{count:>3}x  {book.title} — {book.author}")
        if len(lines) == 2:
            lines.append("No loans recorded yet.")
        self._write("\n".join(lines))

    def show_member_history(self) -> None:
        values = FormDialog.ask(
            self, "Member history", [{"key": "member_id", "label": "Member ID"}]
        )
        if not values:
            return
        try:
            member = self.app.library.get_member(values["member_id"])
            loans = reports.member_history(self.app.library, member.member_id)
        except LibraryError as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return
        lines = [f"History for {member.name} ({member.member_id})", "=" * 36]
        lines.extend(self._loan_lines(loans) if loans else ["No loans recorded."])
        self._write("\n".join(lines))

    def show_policy(self) -> None:
        self._write(reports.policy_summary())


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class LibraryApp(tk.Tk):
    def __init__(self, library: Library, data_path: Path):
        super().__init__()
        self.library = library
        self.data_path = data_path
        self.title("Library Loans Manager")
        self.geometry("1120x700")
        self.minsize(920, 560)

        header = ttk.Frame(self, padding=(10, 8))
        header.pack(fill="x")
        ttk.Label(
            header, text="Library Loans Manager", font=("Segoe UI", 16, "bold")
        ).pack(side="left")
        ttk.Label(
            header,
            text=f"Data file: {data_path}",
            foreground="#666",
        ).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self.books_tab = BooksTab(self.notebook, self)
        self.members_tab = MembersTab(self.notebook, self)
        self.loans_tab = LoansTab(self.notebook, self)
        self.reports_tab = ReportsTab(self.notebook, self)
        self.notebook.add(self.books_tab, text="Books")
        self.notebook.add(self.members_tab, text="Members")
        self.notebook.add(self.loans_tab, text="Loans")
        self.notebook.add(self.reports_tab, text="Reports")

        self.status = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(10, 4)).pack(fill="x")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.bind("<Control-s>", lambda _event: self.after_change("Saved."))

    # -- shared behaviour -------------------------------------------------

    def after_change(self, message: str) -> None:
        if self.save():
            self.refresh_all()
            self.status.set(message)

    def refresh_all(self) -> None:
        for tab in (self.books_tab, self.members_tab, self.loans_tab):
            tab.refresh()
        self.reports_tab.refresh()

    def save(self) -> bool:
        try:
            self.library.save(self.data_path)
            return True
        except (StorageError, LibraryError) as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)
            return False

    def on_close(self) -> None:
        if self.save():
            self.destroy()


def load_library(data_path: Path) -> Library:
    try:
        return Library.load_or_seed(data_path, SAMPLE_DATA)
    except (StorageError, LibraryError) as exc:
        raise SystemExit(f"Could not load the library: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Library Loans Manager (Tkinter interface)")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="path to the JSON data file")
    args = parser.parse_args(argv)

    library = load_library(args.data)
    app = LibraryApp(library, args.data)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
