# Library Loans Manager

A small library lending system built twice — once as a text (command-line)
application and once as a Tkinter desktop GUI — on top of a single, tested
Python core.

The application manages a book catalogue, a membership list and the loans
between them. It records issues, returns and renewals, detects overdue items,
calculates fines, and reports on availability and borrowing activity. All data
is stored in a JSON file, so state survives closing the program.

```
Catalogue ──┐
Members  ───┼──> core (rules, storage, reports) ──> CLI front end
Loans    ──┘                                    └─> Tkinter front end
```

## Features

| Area | What it does |
| --- | --- |
| Books | Add, edit, remove; ISBN-10/13 check-digit validation; duplicate protection |
| Members | Add with generated `M0001`-style ids, edit, deactivate/reactivate, remove |
| Loans | Issue, return, renew; one active loan per copy; maximum 5 concurrent loans |
| Search | Case-insensitive partial search across title, author and ISBN |
| Sort | Title, author, ISBN, year, availability and due date |
| Reports | Availability summary, overdue list with fines, due within 7 days, most borrowed, per-member history |
| Data | JSON persistence with atomic writes; the working file is created on first run |

### Rules enforced by the core

- Loan period: **14 days**; a loan may be renewed once by another 14 days, and
  only while it is not overdue.
- Maximum **5** concurrent loans per member; inactive members cannot borrow.
- Fine: **£0.15 per day** after a **3-day grace period**. The fine is calculated
  on demand from the due date, never stored.
- A book on loan cannot be removed; records with loan history are kept so the
  audit trail stays intact.
- A loan's `returned` date closes it; availability shown on a book is always
  derived from loan history, so the two cannot disagree.

## Requirements

- Python 3.11 or newer (developed on 3.13). Tkinter ships with the standard
  Windows and macOS installers.
- `pytest` for the test suite (the only third-party dependency).

Check that Tkinter works:

```powershell
python -m tkinter
```

That should open a small demonstration window.

## Install and run

From the `library-loans` directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Text version

```powershell
python -m cli.main
```

Options:

```powershell
python -m cli.main --data data/library.json   # choose another data file
python -m cli.main --demo                     # scripted walkthrough for the video
```

### GUI version

```powershell
python -m gui.app
```

Both front ends expose the same operations and read the same data file. The
menu and tab layout are documented in the technical report.

## First run and sample data

`data/sample_library.json` is committed and contains eight titles, four members
and five historical loans (all returned, so the demo data cannot go stale).

On first run the application copies it to `data/library.json`, which is the
working file and is listed in `.gitignore`. Delete `data/library.json` to
restore the sample state. To use a different file, pass `--data <path>`.

> The sample names and email addresses are fictional (`@example.com`).

## Tests

```powershell
python -m pytest
```

The suite covers validation, persistence round-trips, every loan rule, the
search and sort behaviour, all reports, and a scripted pass through the CLI
menus. The GUI is deliberately thin: it calls exactly the same core methods, so
the automated coverage of the rules applies to both front ends. Render it
manually using the checks in the report's test plan.

## Project structure

```
library-loans/
├── core/                  # no tkinter, no input(), no print()
│   ├── models.py          # dataclasses, validation, ISBN checksums, fine rules
│   ├── storage.py         # atomic JSON load/save
│   ├── library.py         # catalogue, members, loans, search index
│   └── reports.py         # sorting and read-only reports
├── cli/main.py            # text menus and prompts
├── gui/app.py             # Tkinter notebook, tree views and form dialog
├── tests/                 # pytest suite
├── data/
│   ├── sample_library.json
│   └── library.json       # generated on first run (git-ignored)
├── requirements.txt
└── pytest.ini
```

### Design notes

- **One core, two interfaces.** `core` never imports `tkinter` and never calls
  `print()` or `input()`. It raises `LibraryError` subclasses; each front end
  decides how to display them. The GUI is therefore a front end, not a rewrite.
- **Data structures.** `dict` keyed by ISBN/member id gives O(1) lookup and
  guarantees uniqueness. Loan history is an append-only `list`. A
  `dict[str, set[str]]` word index narrows searches before the substring filter.
  `heapq.nsmallest` is used for "due soon" because only a few results are
  needed. Sorting relies on Timsort via `sorted(..., key=...)`.
- **Derived state.** A book's `on_loan` flag is recalculated from loan history
  whenever data is loaded, so a corrupted flag cannot survive a restart.
- **Atomic saves.** The JSON is written to a temporary file and moved into place
  with `os.replace`, so an interrupted save cannot truncate the data file.
- **Deterministic tests.** Business logic takes an explicit date where it
  matters (`as_of`, `issued`, `returned`), so tests do not depend on the clock.

## Before you submit

This project was scaffolded with an AI coding assistant while learning the
task. The acknowledgement at the top of each source file and the section below
record that honestly. Your module requires **your own** acknowledgement of the
GenAI you used, at the top of every code file and before the reference list —
replace these notices with an accurate statement and check the wording against
your brief.

- [ ] Replace the GenAI notices with your own accurate acknowledgement.
- [ ] Read through and be able to explain every part of the code you submit.
- [ ] Check the repository is public by opening it in a private window.
- [ ] Confirm no real personal data, passwords or keys are committed.
- [ ] Add a tag/release for the submitted version.

## GenAI acknowledgement

The structure, code and this README were produced with the assistance of an AI
coding assistant (Big Pickle, opencode). All content should be reviewed,
understood and, where your assessment rules require it, rewritten by the author
before submission.

## References

- Python Software Foundation, *The Python Tutorial* — <https://docs.python.org/3/tutorial/>
- Python Software Foundation, *tkinter — Python interface to Tcl/Tk* — <https://docs.python.org/3/library/tkinter.html>
- Python Software Foundation, *dataclasses* — <https://docs.python.org/3/library/dataclasses.html>
- Python Software Foundation, *heapq — Heap queue algorithm* — <https://docs.python.org/3/library/heapq.html>
- Chacon, S. and Straub, B., *Pro Git*, 2nd ed. — <https://git-scm.com/book/en/v2>
- Keele University, *Assessment and Feedback Code of Practice*.
