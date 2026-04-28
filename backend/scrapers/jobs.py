"""Job-listing scraper backed by the python-jobspy library.

Aggregates listings from LinkedIn, Indeed, Glassdoor, Google, and
ZipRecruiter through a single call. Mirrors the shape of
``backend.scrapers.places.scrape_places`` so the rest of the pipeline
(outputs, webhooks, scheduler, dedup) treats results uniformly.
"""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from backend.proxy import proxy_manager

log = logging.getLogger(__name__)

VALID_SITES = {"linkedin", "indeed", "glassdoor", "google", "zip_recruiter", "bayt", "naukri"}
VALID_JOB_TYPES = {"fulltime", "parttime", "internship", "contract"}


def _import_jobspy():
    try:
        from jobspy import scrape_jobs as _scrape  # type: ignore
        return _scrape
    except ImportError as exc:
        raise ImportError(
            "python-jobspy is required for jobs scraping. "
            "Install it with: pip install python-jobspy"
        ) from exc


def _normalize_sites(sites: Any) -> list[str]:
    if not sites:
        return ["indeed", "linkedin", "google", "zip_recruiter"]
    if isinstance(sites, str):
        sites = [s.strip() for s in sites.split(",") if s.strip()]
    cleaned = [s.lower() for s in sites if s and s.lower() in VALID_SITES]
    return cleaned or ["indeed", "linkedin", "google", "zip_recruiter"]


def _df_to_rows(df) -> list[dict]:
    """Convert a pandas DataFrame to plain list[dict], stripping NaN."""
    if df is None or len(df) == 0:
        return []
    rows = df.to_dict(orient="records")
    cleaned: list[dict] = []
    for row in rows:
        out = {}
        for k, v in row.items():
            if v is None:
                continue
            if isinstance(v, float) and math.isnan(v):
                continue
            out[str(k)] = v
        cleaned.append(out)
    return cleaned


def _build_google_search_term(search_term: str, location: str, hours_old: int | None) -> str:
    """Google Jobs uses a single free-text query — assemble from parts."""
    parts = [search_term.strip()] if search_term else []
    if location:
        parts.append(f"jobs near {location}")
    if hours_old:
        if hours_old <= 24:
            parts.append("since yesterday")
        elif hours_old <= 72:
            parts.append("posted in the last 3 days")
        elif hours_old <= 168:
            parts.append("posted in the last week")
    return " ".join(parts).strip()


async def scrape_jobs_async(params: dict) -> list[dict]:
    """Run JobSpy in a worker thread and return list[dict] results.

    Expected ``params`` keys:
      search_term, location, sites, results_wanted, hours_old, distance,
      job_type, is_remote, country_indeed, linkedin_fetch_description,
      description_format.
    """
    scrape = _import_jobspy()

    sites = _normalize_sites(params.get("sites"))
    search_term = (params.get("search_term") or "").strip()
    location = (params.get("location") or "").strip()
    hours_old = params.get("hours_old")
    if hours_old is not None:
        try:
            hours_old = int(hours_old)
        except (TypeError, ValueError):
            hours_old = None

    job_type = (params.get("job_type") or "").strip().lower() or None
    if job_type and job_type not in VALID_JOB_TYPES:
        job_type = None

    results_wanted = int(params.get("results_wanted") or params.get("max_results") or 20)
    distance = params.get("distance")
    if distance is not None:
        try:
            distance = int(distance)
        except (TypeError, ValueError):
            distance = None

    proxies = list(proxy_manager._proxies) if proxy_manager.enabled else None

    kwargs: dict[str, Any] = {
        "site_name": sites,
        "search_term": search_term or None,
        "location": location or None,
        "results_wanted": results_wanted,
        "hours_old": hours_old,
        "country_indeed": (params.get("country_indeed") or "USA"),
        "is_remote": bool(params.get("is_remote", False)),
        "description_format": params.get("description_format") or "markdown",
        "linkedin_fetch_description": bool(params.get("linkedin_fetch_description", False)),
    }
    if distance is not None:
        kwargs["distance"] = distance
    if job_type:
        kwargs["job_type"] = job_type
    if proxies:
        kwargs["proxies"] = proxies
    if "google" in sites:
        kwargs["google_search_term"] = _build_google_search_term(
            search_term, location, hours_old
        )

    log.info(
        "[jobs] scraping sites=%s term=%r location=%r results=%s",
        sites, search_term, location, results_wanted,
    )

    df = await asyncio.to_thread(scrape, **kwargs)
    return _df_to_rows(df)
