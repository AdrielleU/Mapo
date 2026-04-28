"""Tests for the pluggable storage layer."""

import time

import pytest

from backend.storage import get_store
from backend.storage.sqlite_store import SqliteStore


def test_default_store_is_sqlite(monkeypatch):
    monkeypatch.delenv("MAPO_DB_URL", raising=False)
    s = get_store()
    assert isinstance(s, SqliteStore)
    assert s.supports_distributed() is False


def test_explicit_sqlite_url(tmp_path):
    s = get_store(f"sqlite://{tmp_path / 'jobs.db'}")
    assert isinstance(s, SqliteStore)


def test_unsupported_url_raises():
    with pytest.raises(ValueError):
        get_store("mysql://user:pass@host/db")


def test_sqlite_roundtrip(tmp_path):
    path = tmp_path / "jobs.db"
    store = SqliteStore(str(path))
    store.init()

    now = time.time()
    job = {
        "status": "pending",
        "params": {"query": "pizza", "max_results": 50},
        "results": [],
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    store.save_job("job-1", job)

    loaded = store.load_jobs()
    assert "job-1" in loaded
    assert loaded["job-1"]["status"] == "pending"
    assert loaded["job-1"]["params"]["query"] == "pizza"


def test_sqlite_running_jobs_are_marked_failed_on_load(tmp_path):
    """A 'running' job at restart cannot resume — it should be flipped to failed."""
    path = tmp_path / "jobs.db"
    store = SqliteStore(str(path))
    store.init()
    store.save_job("job-1", {
        "status": "running",
        "params": {},
        "results": [],
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    })
    loaded = store.load_jobs()
    assert loaded["job-1"]["status"] == "failed"
    assert "restart" in (loaded["job-1"]["error"] or "").lower()


def test_sqlite_delete(tmp_path):
    store = SqliteStore(str(tmp_path / "jobs.db"))
    store.init()
    store.save_job("j1", {"status": "completed", "params": {}, "results": [], "error": None,
                          "created_at": 0, "updated_at": 0})
    assert "j1" in store.load_jobs()
    store.delete_job("j1")
    assert "j1" not in store.load_jobs()


def test_sqlite_claim_raises():
    """SQLite cannot do distributed claim — must raise a clear error."""
    s = SqliteStore(":memory:")
    s.init()
    with pytest.raises(NotImplementedError) as excinfo:
        s.claim_pending_job("worker-1")
    assert "MAPO_DB_URL" in str(excinfo.value)
