"""PostgreSQL output writer using psycopg2."""

from __future__ import annotations

import json
from typing import Any

from backend.outputs.base import OutputWriter


DEDUP_KEY_CANDIDATES = ("place_id", "job_url", "id")


class PostgresWriter(OutputWriter):
    """Write rows to a PostgreSQL table, upserting on a dedup key.

    Config keys:

    * ``connection`` — a libpq connection string (required).
    * ``table`` — target table name (required).
    * ``dedup_key`` — column to upsert on. If omitted, the writer picks
      the first of ``place_id``, ``job_url``, ``id`` that exists in the
      data; if none exist, rows are inserted without dedup.

    Requires the ``psycopg2`` package at runtime.
    """

    def write(self, data: list[dict], metadata: dict) -> None:
        if not data:
            return

        psycopg2 = _import_psycopg2()

        connection_str = self.config.get("connection")
        table = self.config.get("table")
        if not connection_str:
            raise ValueError("PostgresWriter requires a 'connection' string in config")
        if not table:
            raise ValueError("PostgresWriter requires a 'table' name in config")

        columns = list(data[0].keys())
        _validate_identifiers(table, columns)

        dedup_key = self.config.get("dedup_key")
        if dedup_key and dedup_key not in columns:
            dedup_key = None
        if not dedup_key:
            dedup_key = next((k for k in DEDUP_KEY_CANDIDATES if k in columns), None)

        conn = psycopg2.connect(connection_str)
        try:
            with conn.cursor() as cur:
                # Create table if not exists — all columns TEXT for simplicity.
                col_defs = ", ".join(f'"{col}" TEXT' for col in columns)
                create_sql = (
                    f'CREATE TABLE IF NOT EXISTS "{table}" ({col_defs}'
                )
                if dedup_key:
                    create_sql += f', UNIQUE ("{dedup_key}")'
                create_sql += ")"
                cur.execute(create_sql)

                # Upsert each row.
                col_names = ", ".join(f'"{c}"' for c in columns)
                placeholders = ", ".join(["%s"] * len(columns))
                insert_sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'

                if dedup_key:
                    update_set = ", ".join(
                        f'"{c}" = EXCLUDED."{c}"' for c in columns if c != dedup_key
                    )
                    insert_sql += f' ON CONFLICT ("{dedup_key}") DO UPDATE SET {update_set}'

                for row in data:
                    values = [_serialize_value(row.get(c)) for c in columns]
                    cur.execute(insert_sql, values)

            conn.commit()
        finally:
            conn.close()


def _serialize_value(value: Any) -> str | None:
    """Convert a value to a string suitable for a TEXT column."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _validate_identifiers(table: str, columns: list[str]) -> None:
    """Basic sanity check to prevent SQL injection via identifiers."""
    import re
    pattern = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
    for name in [table] + columns:
        if not pattern.match(name):
            raise ValueError(f"Invalid SQL identifier: {name!r}")


def _import_psycopg2():  # type: ignore[no-untyped-def]
    """Lazy-import psycopg2 with a helpful error message."""
    try:
        import psycopg2
        return psycopg2
    except ImportError:
        raise ImportError(
            "The 'psycopg2' package is required for PostgresWriter. "
            "Install it with: pip install psycopg2-binary"
        ) from None
