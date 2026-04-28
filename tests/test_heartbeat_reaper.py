"""Tests for the heartbeat / reaper interface.

We can't unit-test PostgresStore without a live Postgres, so we exercise:
  * the JobStore base class default no-op behavior
  * a minimal in-memory store that mimics the reap semantics
  * the CLI parser accepts the new flags
"""

from __future__ import annotations

import time
from typing import Any

from backend.storage.base import JobStore


class _FakeDistributedStore(JobStore):
    """Minimal in-memory store that mimics PostgresStore's reap semantics."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def init(self) -> None: pass
    def save_job(self, job_id, job): self.rows[job_id] = dict(job)
    def load_jobs(self): return dict(self.rows)
    def delete_job(self, job_id): self.rows.pop(job_id, None)

    def claim_pending_job(self, worker_id):
        for jid, job in self.rows.items():
            if job["status"] == "pending":
                job["status"] = "running"
                job["worker_id"] = worker_id
                job["heartbeat_at"] = time.time()
                return jid, job
        return None

    def heartbeat(self, job_id):
        if job_id in self.rows and self.rows[job_id]["status"] == "running":
            self.rows[job_id]["heartbeat_at"] = time.time()

    def reap_stale_jobs(self, stale_after_seconds):
        cutoff = time.time() - stale_after_seconds
        n = 0
        for job in self.rows.values():
            if job["status"] == "running" and (job.get("heartbeat_at") or 0) < cutoff:
                job["status"] = "pending"
                job["worker_id"] = None
                job["heartbeat_at"] = None
                job["error"] = "Worker died mid-job; requeued by reaper."
                n += 1
        return n

    def supports_distributed(self): return True


def test_base_heartbeat_is_noop():
    """SqliteStore inherits the no-op default — must not raise."""
    from backend.storage.sqlite_store import SqliteStore
    s = SqliteStore(":memory:")
    s.init()
    s.heartbeat("job-1")  # should not raise


def test_base_reap_returns_zero():
    from backend.storage.sqlite_store import SqliteStore
    s = SqliteStore(":memory:")
    s.init()
    assert s.reap_stale_jobs(60.0) == 0


def test_fake_store_claim_sets_heartbeat():
    s = _FakeDistributedStore()
    s.save_job("j1", {"status": "pending", "params": {}, "results": [], "error": None,
                      "created_at": 0, "updated_at": 0})
    claimed = s.claim_pending_job("worker-A")
    assert claimed is not None
    job_id, job = claimed
    assert job_id == "j1"
    assert job["heartbeat_at"] is not None


def test_fake_store_reaper_requeues_stale_job():
    s = _FakeDistributedStore()
    s.save_job("j1", {
        "status": "running",
        "worker_id": "dead-worker",
        "heartbeat_at": time.time() - 600,  # 10 min ago = stale
        "params": {}, "results": [], "error": None,
        "created_at": 0, "updated_at": 0,
    })
    n = s.reap_stale_jobs(stale_after_seconds=300)
    assert n == 1
    assert s.rows["j1"]["status"] == "pending"
    assert s.rows["j1"]["worker_id"] is None
    assert "reaper" in (s.rows["j1"]["error"] or "")


def test_fake_store_reaper_leaves_fresh_jobs_alone():
    s = _FakeDistributedStore()
    s.save_job("j1", {
        "status": "running",
        "worker_id": "alive-worker",
        "heartbeat_at": time.time() - 5,  # 5s ago = fresh
        "params": {}, "results": [], "error": None,
        "created_at": 0, "updated_at": 0,
    })
    assert s.reap_stale_jobs(stale_after_seconds=300) == 0
    assert s.rows["j1"]["status"] == "running"


def test_fake_store_heartbeat_updates_timestamp():
    s = _FakeDistributedStore()
    s.save_job("j1", {
        "status": "running",
        "heartbeat_at": time.time() - 100,
        "params": {}, "results": [], "error": None,
        "created_at": 0, "updated_at": 0,
    })
    before = s.rows["j1"]["heartbeat_at"]
    time.sleep(0.01)
    s.heartbeat("j1")
    after = s.rows["j1"]["heartbeat_at"]
    assert after > before


def test_cli_parser_has_reaper_flags():
    from backend.cli import _build_parser
    parser = _build_parser()
    args = parser.parse_args([
        "worker",
        "--heartbeat-interval", "10",
        "--reap-interval", "45",
        "--stale-after", "120",
    ])
    assert args.heartbeat_interval == 10.0
    assert args.reap_interval == 45.0
    assert args.stale_after == 120.0
