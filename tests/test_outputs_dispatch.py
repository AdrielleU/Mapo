"""Integration test: pipeline → output target dispatch.

Verifies the wiring fix — that `_write_to_targets` actually invokes the
right writer and that one failing target does not break the others.
"""

import asyncio
import json
import tempfile

import pytest

from backend.outputs import get_writer


def test_csv_writer_via_factory(tmp_path):
    target = {"type": "csv", "path": str(tmp_path / "out.csv")}
    writer = get_writer(target)
    writer.write([{"name": "Foo", "place_id": "abc"}, {"name": "Bar", "place_id": "def"}], {})
    text = (tmp_path / "out.csv").read_text()
    assert "name,place_id" in text
    assert "Foo" in text and "Bar" in text


def test_json_writer_via_factory(tmp_path):
    target = {"type": "json", "path": str(tmp_path / "out.json")}
    writer = get_writer(target)
    writer.write([{"name": "Foo", "nested": [1, 2]}], {})
    data = json.loads((tmp_path / "out.json").read_text())
    assert data == [{"name": "Foo", "nested": [1, 2]}]


def test_unknown_target_type_raises():
    with pytest.raises(ValueError):
        get_writer({"type": "noplace"})


def test_missing_type_raises():
    with pytest.raises(ValueError):
        get_writer({"path": "out.csv"})


def test_write_to_targets_isolates_failures(tmp_path, monkeypatch):
    """A broken target must not stop subsequent targets from running."""
    from backend import server

    good_path = tmp_path / "good.csv"
    targets = [
        {"type": "postgres", "connection": "x"},  # missing 'table' → raises
        {"type": "csv", "path": str(good_path)},
    ]
    monkeypatch.setattr(server.config.outputs, "targets", targets)

    asyncio.run(server._write_to_targets("job-1", [{"name": "Foo"}], {"query": "test"}))
    assert good_path.exists()
    assert "Foo" in good_path.read_text()


def test_interpolate_target_strings_substitutes_placeholders():
    from backend.server import _interpolate_target_strings

    target = {"type": "csv", "path": "./data/{query}_{job_id}.csv", "table": "places"}
    out = _interpolate_target_strings(target, "abc123", "Coffee Shops in NYC!")
    assert "abc123" in out["path"]
    assert "Coffee_Shops_in_NYC" in out["path"]
    # Non-template fields untouched
    assert out["table"] == "places"
    assert out["type"] == "csv"


def test_interpolate_target_handles_empty_query():
    from backend.server import _interpolate_target_strings

    target = {"type": "csv", "path": "./{query}.csv"}
    out = _interpolate_target_strings(target, "j1", "")
    assert "scrape" in out["path"]  # falls back to "scrape"
