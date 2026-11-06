# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Shared pytest fixtures: a small, fully valid library."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.library import Library  # noqa: E402

BOOKS = [
    ("9780132350884", "Clean Code", "Robert C. Martin", 2008),
    ("9780134685991", "Effective Java", "Joshua Bloch", 2018),
    ("9780262033848", "Introduction to Algorithms", "Thomas H. Cormen", 2009),
    ("9780596007126", "Head First Design Patterns", "Eric Freeman", 2004),
    ("9780201633610", "Design Patterns", "Erich Gamma", 1994),
    ("9781617291999", "Python Workout", "Reuven M. Lerner", 2020),
    ("9781491950296", "Programming Python", "Mark Lutz", 2019),
    ("9780321356680", "Effective Java, Second Edition", "Joshua Bloch", 2008),
]

MEMBERS = [
    ("Aisha Khan", "aisha.khan@example.com"),
    ("Ben Okafor", "ben.okafor@example.com"),
    ("Chloe Martin", "chloe.martin@example.com"),
]


@pytest.fixture
def library() -> Library:
    lib = Library()
    for isbn, title, author, year in BOOKS:
        lib.add_book(isbn, title, author, year)
    for name, email in MEMBERS:
        lib.add_member(name, email)
    return lib


@pytest.fixture
def isbns() -> list[str]:
    return [book[0] for book in BOOKS]
