"""CSV output writer."""

from __future__ import annotations

import csv
import json
import os
from typing import Any

from backend.outputs.base import OutputWriter


class CsvWriter(OutputWriter):
    """Write a list of dicts to a CSV file.

    Config keys:

    * ``path`` — destination file path (required).
    """

    def write(self, data: list[dict], metadata: dict) -> None:
        if not data:
            return

        path = self.config.get("path")
        if not path:
            raise ValueError("CsvWriter requires a 'path' in config")

        # Ensure the parent directory exists.
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        # Derive headers from the first row's keys.
        headers = list(data[0].keys())

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            for row in data:
                writer.writerow(_flatten_row(row, headers))


def _flatten_row(row: dict, headers: list[str]) -> dict[str, Any]:
    """Return a copy of *row* where non-scalar values are JSON-serialized."""
    out: dict[str, Any] = {}
    for key in headers:
        value = row.get(key)
        if isinstance(value, (dict, list)):
            out[key] = json.dumps(value, ensure_ascii=False)
        else:
            out[key] = value
    return out
