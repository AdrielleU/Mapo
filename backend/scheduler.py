"""
Cron-based job scheduler for Mapo.

Uses APScheduler to run scraping jobs on a recurring schedule. Jobs run
through the SAME ``run_pipeline()`` as web/CLI requests, so they get all
features (filters, AI, cross-ref, target_new, webhooks, retries).

Schedules are stored in two places:
- mapo.yaml ``scheduler.jobs`` (legacy, read-only)
- ``data/schedules.json`` (managed via API/UI, read-write)
"""
import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path

from backend.config import config

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"
_DB_PATH = _DATA_DIR / "scheduler.db"
_SCHEDULES_PATH = _DATA_DIR / "schedules.json"


def _parse_cron(cron_str: str) -> dict:
    """Parse a 5-field cron string into APScheduler CronTrigger kwargs."""
    parts = cron_str.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Invalid cron {cron_str!r}: expected 5 fields, got {len(parts)}"
        )
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


def load_schedules() -> list[dict]:
    """Load user-managed schedules from data/schedules.json."""
    if not _SCHEDULES_PATH.exists():
        return []
    try:
        with open(_SCHEDULES_PATH) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("Failed to load schedules: %s", e)
        return []


def save_schedules(schedules: list[dict]) -> None:
    """Save schedules to data/schedules.json."""
    _SCHEDULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SCHEDULES_PATH, "w") as f:
        json.dump(schedules, f, indent=2)


class MapoScheduler:
    """
    Manages scheduled scraping jobs backed by APScheduler.

    Reads from both ``config.scheduler.jobs`` (yaml) and
    ``data/schedules.json`` (UI-managed). Hot-reloadable.
    """

    def __init__(self):
        self._scheduler = None

    def _ensure_scheduler(self):
        if self._scheduler is not None:
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        except ImportError:
            raise ImportError(
                "APScheduler is required. Install: pip install apscheduler sqlalchemy"
            )

        os.makedirs(_DATA_DIR, exist_ok=True)
        jobstores = {
            "default": SQLAlchemyJobStore(url=f"sqlite:///{_DB_PATH}"),
        }
        self._scheduler = BackgroundScheduler(jobstores=jobstores)

    def start(self) -> None:
        """Start the scheduler and register all jobs."""
        self._ensure_scheduler()
        self._register_all()
        self._scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

    def reload_schedules(self) -> None:
        """Hot-reload schedules from data/schedules.json (called after API edits)."""
        if self._scheduler is None:
            return
        # Remove existing user-managed jobs (keep yaml ones)
        for job in self._scheduler.get_jobs():
            if job.id.startswith("user_"):
                self._scheduler.remove_job(job.id)
        # Re-register from disk
        self._register_user_schedules()

    def _register_all(self):
        """Register both yaml-defined and user-managed schedules."""
        from apscheduler.triggers.cron import CronTrigger

        # Yaml-defined (legacy, read-only)
        for job_cfg in config.scheduler.jobs:
            name = job_cfg.get("name", "yaml_job")
            cron_str = job_cfg.get("cron", "")
            if not cron_str:
                continue
            try:
                cron_kwargs = _parse_cron(cron_str)
            except ValueError as e:
                logger.error("Skipping yaml job %r: %s", name, e)
                continue
            self._scheduler.add_job(
                func=_run_yaml_job,
                trigger=CronTrigger(**cron_kwargs),
                args=[job_cfg],
                id=f"yaml_{name}",
                name=name,
                replace_existing=True,
            )
            logger.info("Registered yaml schedule: %s (%s)", name, cron_str)

        self._register_user_schedules()

    def _register_user_schedules(self):
        """Register user-managed schedules from data/schedules.json."""
        from apscheduler.triggers.cron import CronTrigger

        for sch in load_schedules():
            if not sch.get("enabled", True):
                continue
            sch_id = sch.get("id")
            cron_str = sch.get("cron", "")
            if not sch_id or not cron_str:
                continue
            try:
                cron_kwargs = _parse_cron(cron_str)
            except ValueError as e:
                logger.error("Skipping user schedule %r: %s", sch.get("name"), e)
                continue
            self._scheduler.add_job(
                func=_run_user_schedule,
                trigger=CronTrigger(**cron_kwargs),
                args=[sch_id],
                id=f"user_{sch_id}",
                name=sch.get("name", "user_job"),
                replace_existing=True,
            )
            logger.info("Registered user schedule: %s (%s)", sch.get("name"), cron_str)


def _run_yaml_job(job_config: dict) -> None:
    """Execute a yaml-defined job using the full pipeline."""
    name = job_config.get("name", "yaml_job")
    logger.info("Yaml job %r started", name)

    # Convert legacy yaml format to ScrapeRequest params
    params = {
        "query": job_config.get("query", ""),
        "country": job_config.get("country", ""),
        "business_type": job_config.get("business_type", ""),
        "max_results": job_config.get("max_results", 100),
        "max_cities": job_config.get("max_cities"),
        "randomize_cities": job_config.get("randomize_cities", True),
        "enable_reviews": job_config.get("enable_reviews", False),
        "enable_ai": job_config.get("enable_ai", False),
    }
    _execute_pipeline_in_thread(params, label=name)


def _run_user_schedule(schedule_id: str) -> None:
    """Execute a user-managed schedule from data/schedules.json."""
    schedules = load_schedules()
    sch = next((s for s in schedules if s.get("id") == schedule_id), None)
    if not sch:
        logger.error("Schedule %s not found", schedule_id)
        return

    name = sch.get("name", "user_job")
    logger.info("User schedule %r started", name)

    params = sch.get("params", {})
    success = _execute_pipeline_in_thread(params, label=name)

    # Update last_run / last_status
    schedules = load_schedules()  # reload in case it changed
    for s in schedules:
        if s.get("id") == schedule_id:
            s["last_run"] = time.time()
            s["last_status"] = "success" if success else "failed"
            break
    save_schedules(schedules)


def _execute_pipeline_in_thread(params: dict, label: str = "scheduled") -> bool:
    """Run the pipeline to completion in a fresh asyncio loop.

    APScheduler runs jobs in background threads, so we need to spin up
    our own event loop here. Returns True on success, False on failure.
    """
    try:
        from backend.server import run_pipeline, _jobs, _save_job

        job_id = str(uuid.uuid4())
        now = time.time()
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "created",
            "params": params,
            "results": [],
            "error": None,
            "created_at": now,
            "updated_at": now,
            "progress": None,
            "_task": None,
        }
        _save_job(job_id)

        # Run the async pipeline in this thread's own event loop
        asyncio.run(run_pipeline(job_id, params))

        job = _jobs.get(job_id, {})
        result_count = len(job.get("results", []))
        status = job.get("status")
        logger.info("Schedule %r finished: %s (%d results)", label, status, result_count)
        return status == "completed"
    except Exception as e:
        logger.error("Schedule %r failed: %s", label, e, exc_info=True)
        return False


# Module-level singleton
scheduler = MapoScheduler()
