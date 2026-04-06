"""Output targets for Mapo — write enriched data to various destinations."""

from __future__ import annotations

from typing import Any

from backend.outputs.base import OutputWriter


def get_writer(target_config: dict[str, Any]) -> OutputWriter:
    """Factory that returns the appropriate :class:`OutputWriter` for
    *target_config*.

    The config dict **must** contain a ``"type"`` key whose value is one of:

    * ``"csv"``
    * ``"json"``
    * ``"postgres"``
    * ``"sheets"``
    * ``"s3"``

    All remaining keys are forwarded to the writer's constructor.
    """
    target_type = target_config.get("type")
    if not target_type:
        raise ValueError("target_config must include a 'type' key (csv, json, postgres, sheets, s3)")

    target_type = target_type.lower().strip()

    if target_type == "csv":
        from backend.outputs.csv_writer import CsvWriter
        return CsvWriter(target_config)

    if target_type == "json":
        from backend.outputs.json_writer import JsonWriter
        return JsonWriter(target_config)

    if target_type == "postgres":
        from backend.outputs.postgres import PostgresWriter
        return PostgresWriter(target_config)

    if target_type == "sheets":
        from backend.outputs.sheets import SheetsWriter
        return SheetsWriter(target_config)

    if target_type == "s3":
        from backend.outputs.s3 import S3Writer
        return S3Writer(target_config)

    raise ValueError(f"Unknown output target type: {target_type!r}")


__all__ = ["get_writer", "OutputWriter"]
