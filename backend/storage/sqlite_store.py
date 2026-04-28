"""SQLite-backed job storage. Default, one file per container.

WAL mode lets readers and a single writer coexist. Multiple processes on the
same host *can* share the file but writes serialize through an OS-level lock,
which makes SQLite a poor fit for true multi-worker distribution. For that,
switch to :class:`backend.storage.postgres_store.PostgresStore`.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from backend.storage.base import JobStore


class SqliteStore(JobStore):
    def __init__(self, path: str) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT,
                    params TEXT,
                    results TEXT,
                    error TEXT,
                    created_at REAL,
                    updated_at REAL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_job(self, job_id: str, job: dict[str, Any]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs
                  (job_id, status, params, results, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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
        if not os.path.exists(self.path):
            return {}
        out: dict[str, dict[str, Any]] = {}
        conn = self._connect()
        try:
            cur = conn.execute(
                "SELECT job_id, status, params, results, error, created_at, updated_at FROM jobs"
            )
            for row in cur.fetchall():
                job_id, status, params, results, error, created_at, updated_at = row
                if status == "running":
                    status = "failed"
                    error = error or "Server restarted while job was running."
                out[job_id] = {
                    "job_id": job_id,
                    "status": status,
                    "params": json.loads(params) if params else {},
                    "results": json.loads(results) if results else [],
                    "error": error,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "progress": None,
                }
        finally:
            conn.close()
        return out

    def delete_job(self, job_id: str) -> None:
        if not os.path.exists(self.path):
            return
        conn = self._connect()
        try:
            conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
            conn.commit()
        finally:
            conn.close()
