"""Postgres-backed job storage with atomic multi-worker claim.

Uses ``SELECT ... FOR UPDATE SKIP LOCKED`` so N worker containers can share
the same database without ever processing the same job twice. Requires the
``psycopg2`` package.
"""

from __future__ import annotations

import json
import time
from typing import Any

from backend.storage.base import JobStore


class PostgresStore(JobStore):
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._psycopg2 = _import_psycopg2()

    def _connect(self):
        return self._psycopg2.connect(self.dsn)

    def init(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS mapo_jobs (
                        job_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        params JSONB NOT NULL DEFAULT '{}'::jsonb,
                        results JSONB NOT NULL DEFAULT '[]'::jsonb,
                        error TEXT,
                        worker_id TEXT,
                        heartbeat_at DOUBLE PRECISION,
                        created_at DOUBLE PRECISION,
                        updated_at DOUBLE PRECISION
                    )
                    """
                )
                # Migration: add heartbeat_at if upgrading from a pre-heartbeat schema.
                cur.execute(
                    "ALTER TABLE mapo_jobs "
                    "ADD COLUMN IF NOT EXISTS heartbeat_at DOUBLE PRECISION"
                )
                # Index makes the SKIP LOCKED claim efficient even with many rows.
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mapo_jobs_status_created "
                    "ON mapo_jobs (status, created_at)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mapo_jobs_status_heartbeat "
                    "ON mapo_jobs (status, heartbeat_at)"
                )
            conn.commit()
        finally:
            conn.close()

    def save_job(self, job_id: str, job: dict[str, Any]) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mapo_jobs
                      (job_id, status, params, results, error, created_at, updated_at)
                    VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (job_id) DO UPDATE SET
                      status = EXCLUDED.status,
                      params = EXCLUDED.params,
                      results = EXCLUDED.results,
                      error = EXCLUDED.error,
                      updated_at = EXCLUDED.updated_at
                    """,
                    (
                        job_id,
                        job.get("status"),
                        json.dumps(job.get("params", {})),
                        json.dumps(job.get("results", [])),
                        job.get("error"),
                        job.get("created_at"),
                        job.get("updated_at"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def load_jobs(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT job_id, status, params, results, error, created_at, updated_at "
                    "FROM mapo_jobs"
                )
                for row in cur.fetchall():
                    job_id, status, params, results, error, created_at, updated_at = row
                    # Same restart semantics as SQLite — but only for THIS process.
                    # Workers in other containers may still legitimately be running it.
                    out[job_id] = {
                        "job_id": job_id,
                        "status": status,
                        "params": params or {},
                        "results": results or [],
                        "error": error,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "progress": None,
                    }
        finally:
            conn.close()
        return out

    def delete_job(self, job_id: str) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM mapo_jobs WHERE job_id = %s", (job_id,))
            conn.commit()
        finally:
            conn.close()

    def claim_pending_job(self, worker_id: str) -> tuple[str, dict[str, Any]] | None:
        """Atomic FIFO claim. Returns the next pending job or None if queue empty."""
        conn = self._connect()
        try:
            now = time.time()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE mapo_jobs
                    SET status = 'running',
                        worker_id = %s,
                        heartbeat_at = %s,
                        updated_at = %s
                    WHERE job_id = (
                        SELECT job_id FROM mapo_jobs
                        WHERE status = 'pending'
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING job_id, params, results, error, created_at, updated_at
                    """,
                    (worker_id, now, now),
                )
                row = cur.fetchone()
            conn.commit()
            if not row:
                return None
            job_id, params, results, error, created_at, updated_at = row
            return job_id, {
                "job_id": job_id,
                "status": "running",
                "params": params or {},
                "results": results or [],
                "error": error,
                "created_at": created_at,
                "updated_at": updated_at,
                "progress": None,
            }
        finally:
            conn.close()

    def heartbeat(self, job_id: str) -> None:
        """Bump heartbeat_at for *job_id* so the reaper knows the worker is alive."""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE mapo_jobs SET heartbeat_at = %s WHERE job_id = %s "
                    "AND status = 'running'",
                    (time.time(), job_id),
                )
            conn.commit()
        finally:
            conn.close()

    # Arbitrary 64-bit constant identifying the "reap" leader-election lock.
    # Any worker can request it; only one holds it at a time. If two workers
    # raced to reap, they'd both UPDATE the same rows and each think they reaped
    # them — the lock just keeps the work cheap.
    _REAP_LOCK_KEY = 0x4D41504F_5245_4150  # ASCII "MAPO REAP"

    def reap_stale_jobs(self, stale_after_seconds: float) -> int:
        """Reset jobs whose worker stopped heartbeating back to 'pending'.

        Cooperatively-locked via pg_try_advisory_lock so only one worker at
        a time runs the scan, even if many call this concurrently.
        """
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_try_advisory_lock(%s)", (self._REAP_LOCK_KEY,))
                got = cur.fetchone()[0]
                if not got:
                    return 0
                try:
                    cutoff = time.time() - stale_after_seconds
                    cur.execute(
                        """
                        UPDATE mapo_jobs
                        SET status = 'pending',
                            error = COALESCE(error, '') ||
                                    CASE WHEN error IS NULL OR error = ''
                                         THEN 'Worker died mid-job; requeued by reaper.'
                                         ELSE ' | requeued by reaper after worker death'
                                    END,
                            worker_id = NULL,
                            heartbeat_at = NULL,
                            updated_at = %s
                        WHERE status = 'running'
                          AND (heartbeat_at IS NULL OR heartbeat_at < %s)
                        """,
                        (time.time(), cutoff),
                    )
                    reaped = cur.rowcount
                    conn.commit()
                    return int(reaped or 0)
                finally:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (self._REAP_LOCK_KEY,))
        finally:
            conn.close()

    def supports_distributed(self) -> bool:
        return True


def _import_psycopg2():
    try:
        import psycopg2
        from psycopg2.extras import Json  # noqa: F401  (validates extras present)
        return psycopg2
    except ImportError:
        raise ImportError(
            "psycopg2 is required for the Postgres job store. "
            "Install with: pip install psycopg2-binary"
        ) from None
