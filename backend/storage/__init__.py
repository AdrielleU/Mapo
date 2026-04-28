"""Pluggable job storage — SQLite by default, Postgres for multi-worker.

Selection is driven by the ``MAPO_DB_URL`` environment variable:

* unset / empty / ``sqlite://...``  → :class:`SqliteStore`
  Default path is ``data/mapo_jobs.db``. One file per container.
* ``postgres://...`` or ``postgresql://...`` → :class:`PostgresStore`
  Multiple containers can share the same database; workers atomically
  claim pending jobs with ``SELECT ... FOR UPDATE SKIP LOCKED``.

The rest of the codebase only sees :class:`JobStore` — it doesn't know or
care which backend is in use.
"""

from __future__ import annotations

import os

from backend.storage.base import JobStore


_DEFAULT_SQLITE_PATH = os.path.join(".", "data", "mapo_jobs.db")


def get_store(url: str | None = None) -> JobStore:
    """Return the configured :class:`JobStore` for this process.

    *url* overrides the ``MAPO_DB_URL`` env var (useful for tests).
    """
    raw = (url if url is not None else os.environ.get("MAPO_DB_URL", "")).strip()

    if not raw or raw.startswith("sqlite://"):
        path = raw[len("sqlite://"):] if raw.startswith("sqlite://") else _DEFAULT_SQLITE_PATH
        path = path or _DEFAULT_SQLITE_PATH
        from backend.storage.sqlite_store import SqliteStore
        return SqliteStore(path)

    if raw.startswith(("postgres://", "postgresql://")):
        from backend.storage.postgres_store import PostgresStore
        return PostgresStore(raw)

    raise ValueError(
        f"Unsupported MAPO_DB_URL scheme: {raw!r}. "
        "Use sqlite://path/to.db or postgresql://user:pass@host/db."
    )


__all__ = ["JobStore", "get_store"]
