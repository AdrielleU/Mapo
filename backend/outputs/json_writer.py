"""JSON output writer."""

from __future__ import annotations

import json
import os

from backend.outputs.base import OutputWriter


class JsonWriter(OutputWriter):
    """Write a list of dicts to a JSON file with ``indent=2``.

    Config keys:

    * ``path`` — destination file path (required).
    """

    def write(self, data: list[dict], metadata: dict) -> None:
        if not data:
            return

        path = self.config.get("path")
        if not path:
            raise ValueError("JsonWriter requires a 'path' in config")

        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
            fh.write("\n")
