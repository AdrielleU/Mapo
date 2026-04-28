"""Abstract base class for job storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class JobStore(ABC):
    """Persistence + atomic-claim interface used by the API and workers.

    The ``claim_pending_job`` method is the only piece that fundamentally
    requires backend support — SQLite serializes via a process-level lock,
    Postgres uses ``SELECT ... FOR UPDATE SKIP LOCKED``.
    """

    @abstractmethod
    def init(self) -> None:
        """Create tables/indexes if missing. Safe to call repeatedly."""

    @abstractmethod
    def save_job(self, job_id: str, job: dict[str, Any]) -> None:
        """Insert or update a single job row."""

    @abstractmethod
    def load_jobs(self) -> dict[str, dict[str, Any]]:
        """Return ``{job_id: job_dict}`` for all persisted jobs.

        Jobs whose status is ``"running"`` at load time should be flipped to
        ``"failed"`` with an explanatory error — they were interrupted by a
        restart and cannot resume cleanly.
        """

    @abstractmethod
    def delete_job(self, job_id: str) -> None:
        """Remove a single job row. No-op if it doesn't exist."""

    def claim_pending_job(self, worker_id: str) -> tuple[str, dict[str, Any]] | None:
        """Atomically claim one ``status='pending'`` job for processing.

        Returns ``(job_id, job_dict)`` on success, or ``None`` when the queue
        is empty. Default implementation raises — backends that support
        distributed work must override this.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support distributed claim. "
            "Use the Postgres backend (set MAPO_DB_URL=postgresql://...) "
            "to run multiple worker containers against a shared queue."
        )

    def heartbeat(self, job_id: str) -> None:
        """Mark *job_id* as still alive. Called periodically by the worker
        processing the job so the reaper can tell it from a crashed one.

        Default: no-op (single-process backends don't need it).
        """

    def reap_stale_jobs(self, stale_after_seconds: float) -> int:
        """Find jobs whose heartbeat has lapsed past *stale_after_seconds*
        and reset them to ``status='pending'`` so another worker can pick them up.

        Returns the number of jobs reaped. Default: no-op (single-process
        backends can't have stranded jobs the way a distributed cluster can).
        """
        return 0

    def supports_distributed(self) -> bool:
        """Whether this backend supports multi-worker job claiming."""
        return False
