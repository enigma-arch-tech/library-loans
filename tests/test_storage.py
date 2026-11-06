# ---------------------------------------------------------------------------
# GenAI acknowledgement (replace before submission)
# This file was produced with the assistance of an AI coding assistant
# (Big Pickle, opencode). Review it, understand it, and replace this notice
# with an acknowledgement in the form required by your module before you
# submit this work.
# ---------------------------------------------------------------------------

"""Tests for the JSON persistence layer."""

from __future__ import annotations

import json

import pytest

from core.storage import StorageError, ensure_data_file, load_json, save_json


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "nested" / "library.json"
    data = {"schema_version": 1, "books": [{"isbn": "9780132350884"}]}
    save_json(path, data)
    assert load_json(path) == data


def test_save_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "library.json"
    save_json(path, {"a": 1})
    save_json(path, {"a": 2})
    assert load_json(path) == {"a": 2}
    leftovers = [item.name for item in tmp_path.iterdir() if item.suffix == ".tmp"]
    assert leftovers == []


def test_missing_file_raises(tmp_path):
    with pytest.raises(StorageError):
        load_json(tmp_path / "nope.json")


def test_corrupt_json_raises_with_clear_message(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StorageError) as info:
        load_json(path)
    assert "not valid JSON" in str(info.value)


def test_non_object_json_is_rejected(tmp_path):
    path = tmp_path / "list.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(StorageError):
        load_json(path)


def test_ensure_data_file_seeds_once(tmp_path):
    sample = tmp_path / "sample.json"
    save_json(sample, {"seed": True})
    working = tmp_path / "data" / "library.json"

    ensure_data_file(working, sample)
    assert load_json(working) == {"seed": True}

    save_json(working, {"seed": False})
    ensure_data_file(working, sample)
    assert load_json(working) == {"seed": False}


def test_ensure_data_file_without_sample_is_a_no_op(tmp_path):
    working = tmp_path / "library.json"
    ensure_data_file(working, tmp_path / "missing.json")
    assert not working.exists()
