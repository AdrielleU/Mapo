"""Integration test for PostgresStore — exercises real SQL against a live DB.

Skipped automatically unless ``MAPO_TEST_PG_URL`` is set to a libpq DSN, e.g.::

    MAPO_TEST_PG_URL=postgresql://mapo:mapo@localhost:5432/mapo_test \
        venv/bin/python -m pytest tests/test_postgres_integration.py -v

The fastest local Postgres for this:

    docker run --rm -d --name mapo-pg-test \
        -e POSTGRES_USER=mapo -e POSTGRES_PASSWORD=mapo -e POSTGRES_DB=mapo_test \
        -p 5433:5432 postgres:16-alpine

    MAPO_TEST_PG_URL=postgresql://mapo:mapo@localhost:5433/mapo_test pytest -v ...

The test owns the ``mapo_jobs`` table — it's truncated at the start of each
test, so don't point this at a database that has real job data in it.
"""

from __future__ import annotations

import os
import time

import pytest

PG_URL = os.environ.get("MAPO_TEST_PG_URL", "").strip()

# Skip the entire module if no DSN is configured or psycopg2 isn't installed.
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 not installed")
if not PG_URL:
    pytest.skip("MAPO_TEST_PG_URL not set; skipping live Postgres tests", allow_module_level=True)


@pytest.fixture
def store():
    from backend.storage.postgres_store import PostgresStore
    s = PostgresStore(PG_URL)
    s.init()
    # Clean slate per test
    conn = psycopg2.connect(PG_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE mapo_jobs")
        conn.commit()
    finally:
        conn.close()
    yield s


def _make_job(status="pending", **overrides):
    return {
        "status": status,
        "params": {"query": "coffee"},
        "results": [],
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
        **overrides,
    }


def test_init_is_idempotent(store):
    """Calling init() twice (e.g. across container restarts) must not error."""
    store.init()
    store.init()


def test_save_and_load_roundtrip(store):
    store.save_job("j1", _make_job(status="pending"))
    loaded = store.load_jobs()
    assert "j1" in loaded
    assert loaded["j1"]["status"] == "pending"
    assert loaded["j1"]["params"]["query"] == "coffee"


def test_claim_returns_none_when_empty(store):
    assert store.claim_pending_job("worker-A") is None


def test_claim_promotes_pending_to_running(store):
    store.save_job("j1", _make_job(status="pending"))
    claimed = store.claim_pending_job("worker-A")
    assert claimed is not None
    job_id, job = claimed
    assert job_id == "j1"
    assert job["status"] == "running"
    # Heartbeat should be set as part of the atomic claim
    loaded = store.load_jobs()
    assert loaded["j1"]["status"] == "running"


def test_two_workers_never_claim_same_job(store):
    """The whole point of FOR UPDATE SKIP LOCKED — race-free."""
    store.save_job("j1", _make_job(status="pending"))
    a = store.claim_pending_job("worker-A")
    b = store.claim_pending_job("worker-B")
    assert a is not None
    assert b is None  # B saw an empty queue, didn't double-claim


def test_claim_is_fifo(store):
    now = time.time()
    store.save_job("old", _make_job(status="pending", created_at=now - 100, updated_at=now - 100))
    store.save_job("new", _make_job(status="pending", created_at=now, updated_at=now))
    claimed = store.claim_pending_job("worker-A")
    assert claimed[0] == "old"


def test_heartbeat_updates_timestamp(store):
    store.save_job("j1", _make_job(status="pending"))
    store.claim_pending_job("worker-A")

    conn = psycopg2.connect(PG_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT heartbeat_at FROM mapo_jobs WHERE job_id = 'j1'")
            before = cur.fetchone()[0]
        time.sleep(0.05)
        store.heartbeat("j1")
        with conn.cursor() as cur:
            cur.execute("SELECT heartbeat_at FROM mapo_jobs WHERE job_id = 'j1'")
            after = cur.fetchone()[0]
    finally:
        conn.close()
    assert after > before


def test_heartbeat_no_op_for_non_running(store):
    """A worker shouldn't be able to keep a 'completed' job alive."""
    store.save_job("j1", _make_job(status="completed"))
    store.heartbeat("j1")  # should not raise, should not change anything

    conn = psycopg2.connect(PG_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT heartbeat_at FROM mapo_jobs WHERE job_id = 'j1'")
            assert cur.fetchone()[0] is None
    finally:
        conn.close()


def test_reaper_requeues_stale_running_job(store):
    """End-to-end of the failure mode that motivated this whole feature."""
    store.save_job("j1", _make_job(status="pending"))
    store.claim_pending_job("dead-worker")

    # Manually backdate the heartbeat to simulate worker death
    conn = psycopg2.connect(PG_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE mapo_jobs SET heartbeat_at = %s WHERE job_id = 'j1'",
                (time.time() - 600,),
            )
        conn.commit()
    finally:
        conn.close()

    n = store.reap_stale_jobs(stale_after_seconds=300)
    assert n == 1
    loaded = store.load_jobs()
    assert loaded["j1"]["status"] == "pending"
    assert "reaper" in (loaded["j1"]["error"] or "")

    # Another worker should now be able to pick it up
    claimed = store.claim_pending_job("worker-B")
    assert claimed is not None and claimed[0] == "j1"


def test_reaper_leaves_fresh_running_jobs_alone(store):
    store.save_job("j1", _make_job(status="pending"))
    store.claim_pending_job("alive-worker")  # heartbeat set to now()
    n = store.reap_stale_jobs(stale_after_seconds=300)
    assert n == 0
    loaded = store.load_jobs()
    assert loaded["j1"]["status"] == "running"


def test_delete_job_removes_row(store):
    store.save_job("j1", _make_job())
    assert "j1" in store.load_jobs()
    store.delete_job("j1")
    assert "j1" not in store.load_jobs()


def test_init_migrates_pre_heartbeat_table(store):
    """Simulate upgrading from a Mapo version that didn't have heartbeat_at."""
    conn = psycopg2.connect(PG_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE mapo_jobs DROP COLUMN heartbeat_at")
        conn.commit()
    finally:
        conn.close()

    # init() should add it back without erroring
    store.init()

    conn = psycopg2.connect(PG_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'mapo_jobs' AND column_name = 'heartbeat_at'"
            )
            assert cur.fetchone() is not None
    finally:
        conn.close()


def test_advisory_lock_serializes_concurrent_reapers(store):
    """If two reapers run at the same time, only one does the work.

    We test this by holding the lock manually and confirming the next
    reaper call returns 0 (no rows reaped) instead of contending.
    """
    store.save_job("j1", _make_job(status="pending"))
    store.claim_pending_job("dead-worker")

    # Hold the lock from this connection
    conn = psycopg2.connect(PG_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", (store._REAP_LOCK_KEY,))
            # While we hold it, the store's reaper should yield (return 0)
            n = store.reap_stale_jobs(stale_after_seconds=0)
            assert n == 0
            cur.execute("SELECT pg_advisory_unlock(%s)", (store._REAP_LOCK_KEY,))
        conn.commit()
    finally:
        conn.close()

    # Now the lock is free — reaper can do its work
    n2 = store.reap_stale_jobs(stale_after_seconds=0)
    assert n2 == 1
