"""
Cron-based job scheduler for Mapo.

Uses APScheduler to run scraping jobs on a recurring schedule.
Job definitions come from ``backend.config.config.scheduler``.

Usage::

    from backend.scheduler import scheduler
    scheduler.start()
    # ... scheduler runs in background ...
    scheduler.stop()
"""
import logging
import os
from pathlib import Path

from backend.config import config

logger = logging.getLogger(__name__)

# Path for the persistent SQLite job store
_DATA_DIR = Path(__file__).parent.parent / "data"
_DB_PATH = _DATA_DIR / "scheduler.db"


def _parse_cron(cron_str: str) -> dict:
    """
    Parse a standard 5-field cron string into APScheduler CronTrigger kwargs.

    Format: ``minute hour day month day_of_week``

    Examples::

        "0 8 * * 1"   -> every Monday at 08:00
        "30 6 * * *"   -> every day at 06:30
    """
    parts = cron_str.strip().split()
    if len(parts) != 5:
        raise ValueError(
            f"Invalid cron string {cron_str!r}: expected 5 fields "
            f"(minute hour day month day_of_week), got {len(parts)}"
        )

    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


class MapoScheduler:
    """
    Manages scheduled scraping jobs backed by APScheduler.

    Reads job definitions from ``config.scheduler.jobs`` and registers
    them as cron-triggered background jobs.
    """

    def __init__(self):
        self._scheduler = None
        self._jobs_config: list[dict] = config.scheduler.jobs

    def _ensure_scheduler(self):
        """Lazily create the APScheduler BackgroundScheduler instance."""
        if self._scheduler is not None:
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            from apscheduler.triggers.cron import CronTrigger  # noqa: F401
        except ImportError:
            raise ImportError(
                "APScheduler is required for the scheduling feature. "
                "Install it with: pip install apscheduler sqlalchemy"
            )

        os.makedirs(_DATA_DIR, exist_ok=True)

        jobstores = {
            "default": SQLAlchemyJobStore(url=f"sqlite:///{_DB_PATH}"),
        }
        self._scheduler = BackgroundScheduler(jobstores=jobstores)

    def start(self) -> None:
        """Register all configured jobs and start the background scheduler."""
        self._ensure_scheduler()

        from apscheduler.triggers.cron import CronTrigger

        for job_cfg in self._jobs_config:
            name = job_cfg.get("name", "unnamed_job")
            cron_str = job_cfg.get("cron", "")
            if not cron_str:
                logger.warning("Skipping job %r — no cron expression", name)
                continue

            try:
                cron_kwargs = _parse_cron(cron_str)
            except ValueError as exc:
                logger.error("Skipping job %r: %s", name, exc)
                continue

            trigger = CronTrigger(**cron_kwargs)

            self._scheduler.add_job(
                func=self._run_job,
                trigger=trigger,
                args=[job_cfg],
                id=name,
                name=name,
                replace_existing=True,
            )
            logger.info(
                "Registered scheduled job %r (cron=%s, max_results=%s)",
                name,
                cron_str,
                job_cfg.get("max_results", "default"),
            )

        self._scheduler.start()
        logger.info(
            "Scheduler started with %d job(s)",
            len(self._jobs_config),
        )

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

    @staticmethod
    def _run_job(job_config: dict) -> None:
        """
        Execute a single scheduled scrape job.

        Steps:
            1. Call the scraper pipeline with the job's query/params
            2. Write results to the configured output target
            3. Fire a webhook notification if configured
            4. Log start/completion/errors
        """
        import csv as _csv
        import json as _json

        name = job_config.get("name", "unnamed")
        query = job_config.get("query", "")
        max_results = job_config.get("max_results", 100)
        output_target = job_config.get("output_target", "csv")
        output_path = job_config.get("output_path", "")

        logger.info("Job %r started — query=%r, max_results=%d", name, query, max_results)

        try:
            from backend.scrapers.places import scrape_places

            data_input = {
                "query": query,
                "max_results": max_results,
            }
            results = scrape_places(data_input)

            if not results:
                logger.warning("Job %r produced no results", name)
                return

            # Write output
            if output_path:
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

                if output_target == "json":
                    with open(output_path, "w", encoding="utf-8") as f:
                        _json.dump(results, f, indent=2, ensure_ascii=False, default=str)
                else:
                    # Default to CSV
                    keys = list(results[0].keys())
                    with open(output_path, "w", newline="", encoding="utf-8") as f:
                        writer = _csv.DictWriter(f, fieldnames=keys)
                        writer.writeheader()
                        writer.writerows(results)

                logger.info(
                    "Job %r completed — %d records written to %s",
                    name,
                    len(results),
                    output_path,
                )

            # Fire webhook if configured
            try:
                from backend.config import config as _cfg

                if _cfg.webhooks.enabled and _cfg.webhooks.urls:
                    try:
                        from backend.webhooks import fire_webhook

                        fire_webhook({
                            "event": "scheduled_job_complete",
                            "job_name": name,
                            "record_count": len(results),
                            "output_path": output_path,
                        })
                    except ImportError:
                        logger.debug("Webhooks module not available, skipping notification")
            except Exception as exc:
                logger.warning("Webhook notification failed for job %r: %s", name, exc)

        except Exception as exc:
            logger.error("Job %r failed: %s", name, exc, exc_info=True)


# Module-level singleton
scheduler = MapoScheduler()
