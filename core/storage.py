# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""JSON persistence.

A single JSON document holds the whole library. Writes are atomic: the new
document is written to a temporary file in the same directory and then moved
over the old one with ``os.replace``, so an interrupted save cannot leave a
half-written data file behind.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class StorageError(Exception):
    """The data file could not be read or written."""


def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise StorageError(f"Data file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise StorageError(f"Data file is not valid JSON ({exc}).") from None
    except OSError as exc:
        raise StorageError(f"Could not read {path}: {exc}") from None

    if not isinstance(data, dict):
        raise StorageError("Data file must contain a JSON object.")
    return data


def save_json(path: str | Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    temp_name = ""
    try:
        handle, temp_name = tempfile.mkstemp(
            prefix=f"{path.name}.", suffix=".tmp", dir=path.parent
        )
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            handle = None  # fdopen now owns the descriptor
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        raise StorageError(f"Could not write {path}: {exc}") from None
    finally:
        if handle is not None:
            os.close(handle)
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def ensure_data_file(path: str | Path, sample_path: str | Path) -> None:
    """Create ``path`` from ``sample_path`` on first run, if it is missing."""
    path = Path(path)
    if path.exists():
        return
    sample = Path(sample_path)
    if not sample.exists():
        return
    save_json(path, load_json(sample))
