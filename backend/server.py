"""
Mapo FastAPI server — Google Maps scraper pipeline.

Replaces the old Botasaurus-based server with a pure FastAPI + asyncio
architecture.  Jobs are tracked in-memory with SQLite persistence.
"""
import asyncio
import csv
import io
import json
import os
import random
import re
import sqlite3
import time
import uuid
import urllib.parse
from urllib.parse import urlparse

import httpx

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.scrapers.places import scrape_places
from backend.scrapers.reviews import scrape_reviews
from backend.scrapers.social import (
    scrape_social,
    get_website_contacts,
    make_empty_social,
    FAILED_DUE_TO_CREDITS_EXHAUSTED,
    FAILED_DUE_TO_NOT_SUBSCRIBED,
    FAILED_DUE_TO_UNKNOWN_ERROR,
)
from backend.scrapers.filters import filter_places, sort_dict_by_keys
from backend.data.countries import get_cities
from backend.data.states import get_states, get_state_cities
from backend.utils import remove_nones, extract_path
from backend.progress import JobProgress
from backend.config import config, _load_ui_settings, _save_ui_settings, reload_config
from backend.webhooks import webhook_manager
from backend.enrichment.email_quality import analyze_emails
from backend.notifications import send_notification, send_notification_async, detect_provider
from backend.auth import (
    AUTH_ENABLED, is_authenticated,
    login_page, login_submit, logout, check_auth_api,
)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="Mapo")


# ---------------------------------------------------------------------------
# Auth middleware — redirects to /auth/login when auth is enabled
# ---------------------------------------------------------------------------

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Always allow auth routes, static assets, and health check
    if (not AUTH_ENABLED
            or path.startswith("/auth/")
            or path.startswith("/static/")
            or path == "/api/v1/health"):
        return await call_next(request)

    if not is_authenticated(request):
        # API requests get 401, browser requests get redirected
        if path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Authentication required."})
        return RedirectResponse("/auth/login", status_code=302)

    return await call_next(request)


# Auth routes
app.add_api_route("/auth/login", login_page, methods=["GET"])
app.add_api_route("/auth/login", login_submit, methods=["POST"])
app.add_api_route("/auth/logout", logout, methods=["GET"])
app.add_api_route("/auth/check", check_auth_api, methods=["GET"])

# ---------------------------------------------------------------------------
# Job store
# ---------------------------------------------------------------------------

_jobs: dict = {}
_ws_clients: dict[str, list[WebSocket]] = {}
_DB_PATH = os.path.join(".", "data", "mapo_jobs.db")


def _db_connect():
    """Open a SQLite connection with WAL mode for better concurrency."""
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db():
    """Create the jobs table if it does not exist."""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = _db_connect()
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
    conn.close()


def _save_job(job_id: str):
    """Persist a single job to SQLite."""
    job = _jobs.get(job_id)
    if job is None:
        return
    conn = _db_connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO jobs (job_id, status, params, results, error, created_at, updated_at)
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
    conn.close()


def _load_jobs():
    """Load all persisted jobs from SQLite into _jobs."""
    if not os.path.exists(_DB_PATH):
        return
    conn = _db_connect()
    cursor = conn.execute("SELECT job_id, status, params, results, error, created_at, updated_at FROM jobs")
    for row in cursor.fetchall():
        job_id, status, params, results, error, created_at, updated_at = row
        # Do not reload running jobs — they are stale after restart
        if status == "running":
            status = "failed"
            error = error or "Server restarted while job was running."
        _jobs[job_id] = {
            "job_id": job_id,
            "status": status,
            "params": json.loads(params) if params else {},
            "results": json.loads(results) if results else [],
            "error": error,
            "created_at": created_at,
            "updated_at": updated_at,
            "progress": None,
        }
    conn.close()


# ---------------------------------------------------------------------------
# Query helpers (ported from old server.py, bt/cl replaced)
# ---------------------------------------------------------------------------

def _clean_query(s):
    """Normalize a query string."""
    if isinstance(s, str):
        return re.sub(r"\s+", " ", s.strip().lower())
    return s


def _is_url(s):
    """Check whether *s* looks like a URL."""
    return s.startswith("http://") or s.startswith("https://")


def _split_gmaps_links(links):
    """Separate Google Maps search URLs from place URLs."""
    search_queries: list[str] = []
    place_links: list[str] = []

    for link in links:
        path = extract_path(link)
        if path.startswith("/maps/search"):
            query = urllib.parse.unquote_plus(
                path.lstrip("/maps/search/").split("/")[0]
            ).strip()
            if query:
                search_queries.append(query)
            elif "query_place_id" in link:
                place_links.append(link)
        else:
            place_links.append(link)

    return place_links, search_queries


def split_task_by_query(data):
    """Split a task into sub-tasks based on queries or country + business_type."""
    if data.get("country"):
        # If a state is given (US only for now), use state cities instead
        if data.get("state") and data["country"] == "US":
            cities = get_state_cities(data["country"], data["state"])
        else:
            cities = get_cities(data["country"])

        if data.get("randomize_cities"):
            cities = cities.copy()
            random.shuffle(cities)

        if data.get("max_cities"):
            cities = cities[: data["max_cities"]]

        queries = [f"{data['business_type']} in {city}" for city in cities]
        data_copy = {k: v for k, v in data.items() if k != "queries"}
        return [{**data_copy, "query": _clean_query(q)} for q in queries]

    queries = data.get("queries", [])
    data_copy = {k: v for k, v in data.items() if k != "queries"}

    urls = [q for q in queries if _is_url(q)]
    place_links, search_queries = _split_gmaps_links(urls)

    url_set = set(urls)
    for q in queries:
        if q not in url_set:
            search_queries.append(q)

    tasks = [{**data_copy, "query": _clean_query(q)} for q in search_queries]

    if place_links:
        tasks.insert(0, {**data_copy, "links": place_links, "query": "Links"})

    return tasks


# ---------------------------------------------------------------------------
# Social / review merging
# ---------------------------------------------------------------------------

def _merge_social_data(places, social_results, should_scrape):
    """Merge social scraper results back into place dicts."""
    success: dict = {}
    errors: dict = {}

    for detail in (social_results or []):
        if detail is None:
            continue
        pid = detail.get("place_id")
        if detail.get("error") is None:
            success[pid] = detail
        else:
            errors[pid] = detail["error"]

    for place in places:
        pid = place.get("place_id")

        if pid in success:
            place.update(success[pid].get("data", {}))
        elif pid in errors:
            err = errors[pid]
            if err == FAILED_DUE_TO_CREDITS_EXHAUSTED:
                msg = "Credit exhaustion. Upgrade at RapidAPI."
            elif err == FAILED_DUE_TO_NOT_SUBSCRIBED:
                msg = "Not subscribed to API. Subscribe at RapidAPI."
            else:
                msg = "Unknown error getting social details."
            place.update(make_empty_social(msg))
        elif place.get("website"):
            if should_scrape:
                place.update(make_empty_social("Failed to get social details."))
            else:
                place.update(make_empty_social("Provide API Key"))
        else:
            place.update(make_empty_social())

    return places


def _merge_reviews(places, review_results):
    """Merge scraped reviews back into place dicts."""
    review_map: dict = {}
    for r in (review_results or []):
        review_map[r["place_id"]] = r["reviews"]

    for place in places:
        place["detailed_reviews"] = review_map.get(place["place_id"], [])

    return places


# ---------------------------------------------------------------------------
# Canonical output field order
# ---------------------------------------------------------------------------

SOCIAL_MEDIA_KEYS = [
    "emails", "phones", "linkedin", "twitter", "facebook",
    "youtube", "instagram", "pinterest", "github", "snapchat", "tiktok",
]

DETECTION_KEYS = [
    "technologies", "cms", "software_list", "software",
    "ad_pixels", "has_contact_form", "form_provider",
    "website_quality_score",
]

OUTPUT_FIELDS = [
    # Core identity
    "place_id", "name", "description", "main_category", "categories",
    "rating", "reviews", "price_range", "status",
    # Contact
    "phone", "phone_international", "website", "address",
    "detailed_address", "coordinates", "plus_code", "time_zone",
    "link", "reviews_link",
    # Ownership & signals
    "owner", "owner_link", "can_claim",
    "is_spending_on_ads", "is_temporarily_closed", "is_permanently_closed",
    # Social / enrichment
] + SOCIAL_MEDIA_KEYS + [
    # Business details
    "hours", "closed_on", "service_options", "about",
    "menu", "reservations", "order_online_links",
    # Reviews intelligence
    "reviews_per_rating", "review_keywords", "owner_response_rate",
    "featured_question",
    # Competition
    "competitors",
    # Media
    "featured_image", "images", "image_count",
    # Timing / traffic
    "popular_times", "most_popular_times",
    # Detection
] + DETECTION_KEYS + [
    # Email intelligence
    "best_email", "best_email_type", "best_email_score", "email_recommendation",
    # AI scoring
    "lead_score", "icp_match", "pitch_summary", "suggested_approach",
    "review_sentiment", "review_themes",
    # Reviews data
    "featured_reviews", "detailed_reviews",
    # Meta
    "cid", "data_id", "query",
]


# ---------------------------------------------------------------------------
# Export Presets — common field subsets for downstream tools
# ---------------------------------------------------------------------------
# Each preset defines a subset of fields that's optimized for a specific tool.
# Users can pick a preset OR provide a custom field list.

EXPORT_PRESETS = {
    "minimal": [
        "name", "address", "phone", "website", "main_category", "rating", "reviews",
    ],
    "clay": [
        # Clay uses domain as the universal key + waterfall enrichment
        "name", "website", "address", "city", "state", "country_code",
        "phone", "main_category", "rating", "reviews",
    ],
    "apollo": [
        # Apollo wants company + domain to enrich
        "name", "website", "address", "phone", "main_category",
    ],
    "hubspot": [
        # HubSpot Companies object fields (camelCase mapping happens in n8n/Make)
        "name", "website", "phone", "address", "main_category",
        "rating", "reviews", "best_email",
    ],
    "instantly": [
        # Instantly campaign import — needs email + first/last/company
        "name", "best_email", "phone", "website", "main_category", "address",
    ],
    "n8n": [
        # Comprehensive payload for n8n/Make/Zapier workflows
        "place_id", "name", "main_category", "categories", "rating", "reviews",
        "phone", "website", "address", "detailed_address", "coordinates",
        "owner", "is_spending_on_ads", "can_claim", "best_email",
    ],
    "leads": [
        # Sales-focused: contact info + signals
        "name", "phone", "website", "address", "rating", "reviews",
        "main_category", "owner", "is_spending_on_ads", "can_claim",
        "best_email", "best_email_score",
    ],
    "geo": [
        # Mapping/geo analysis only
        "name", "main_category", "coordinates", "address", "rating", "reviews",
    ],
    "full": [],  # empty = all fields
}


def select_fields(places: list[dict], fields: list[str] | None) -> list[dict]:
    """Filter each place dict to only the requested fields."""
    if not fields:
        return places
    return [{k: p.get(k) for k in fields} for p in places]


def resolve_export_fields(preset: str = "", fields: list[str] | None = None) -> list[str] | None:
    """Resolve a preset name + custom fields list into the final field list."""
    if fields:
        return fields
    if preset:
        return EXPORT_PRESETS.get(preset.lower())
    return None


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    query: str = ""
    country: str = ""
    state: str = ""
    business_type: str = ""
    max_results: int = 100
    max_cities: int | None = None
    randomize_cities: bool = True
    lang: str = ""
    coordinates: str = ""
    zoom_level: float = 14
    radius_meters: int | None = None
    enable_reviews: bool = False
    max_reviews: int = 20
    reviews_sort: str = "newest"
    enrichment_api_key: str = ""
    enable_ai: bool = False
    # Per-job webhooks (paste URL in UI, no yaml needed)
    webhook_url: str = ""
    webhook_headers: dict = {}
    error_webhook_url: str = ""
    # Cross-reference dedup against an existing CSV/JSON
    skip_existing_csv: str = ""           # file path (CLI usage)
    skip_existing_csv_data: str = ""      # base64-encoded CSV (web upload)
    skip_existing_field: str = "place_id" # field to dedup on
    target_new: int | None = None         # target number of NEW places after cross-ref
    target_buffer: float = 2.0            # multiply max_results by this to compensate
    # Field selection (export only specific fields)
    export_preset: str = ""               # minimal, clay, apollo, hubspot, instantly, n8n, leads, geo, full
    export_fields: list[str] = []         # custom field list (overrides preset)
    # Retry on failure
    max_retries: int = 2            # 0 = no retries, 2 = 3 total attempts
    retry_delay: int = 30           # seconds between retries (multiplied by attempt)
    # Server-side result filters
    has_website: bool | None = None
    min_reviews: int | None = None
    min_rating: float | None = None
    max_rating: float | None = None
    has_phone: bool | None = None
    skip_closed: bool = False
    category_in: list[str] | None = None
    price_range: str | list[str] | None = None


class EnrichRequest(BaseModel):
    websites: list[str]
    provider: str = "rapidapi"
    api_key: str = ""


# ---------------------------------------------------------------------------
# WebSocket helpers
# ---------------------------------------------------------------------------

async def _broadcast(job_id: str, message: dict):
    """Send a JSON message to all WebSocket clients watching *job_id*."""
    for ws in list(_ws_clients.get(job_id, [])):
        try:
            await ws.send_json(message)
        except Exception:
            _ws_clients[job_id].remove(ws)


# ---------------------------------------------------------------------------
# Auto-export + webhook helpers
# ---------------------------------------------------------------------------

def _flatten_for_csv(row: dict) -> dict:
    """JSON-encode nested values so CSV can write them as strings."""
    return {k: (json.dumps(v, default=str) if isinstance(v, (list, dict)) else v) for k, v in row.items()}


def _auto_export(job_id: str, results: list[dict]):
    """Auto-save results as CSV + JSON to data/exports/ on completion."""
    if not results:
        return
    export_dir = os.path.join("data", "exports")
    os.makedirs(export_dir, exist_ok=True)

    # CSV
    try:
        csv_path = os.path.join(export_dir, f"mapo_{job_id}.csv")
        fieldnames = list(results[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in results:
                writer.writerow(_flatten_for_csv(row))
    except Exception as e:
        print(f"[Mapo] Auto-export CSV failed: {e}")

    # JSON
    try:
        json_path = os.path.join(export_dir, f"mapo_{job_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Mapo] Auto-export JSON failed: {e}")


def _fire_webhook(job_id: str, event_type: str, result_count: int,
                   results: list[dict] | None = None):
    """Fire webhook notification if configured.

    Sends to global webhook URLs from config AND per-job webhook URL
    if provided in the job params.  The payload includes the full results
    array so downstream tools (n8n, Make, Zapier) can process lead data
    without a second API call.
    """
    try:
        job = _jobs.get(job_id, {})
        params = job.get("params", {})

        base_payload = {
            "job_id": job_id,
            "query": params.get("query", ""),
            "result_count": result_count,
            "timestamp": time.time(),
            "download_csv": f"/api/v1/jobs/{job_id}/download?format=csv",
            "download_json": f"/api/v1/jobs/{job_id}/download?format=json",
        }

        # Include results in payload (capped at 500 to avoid huge payloads)
        if results:
            base_payload["results"] = results[:500]
            if len(results) > 500:
                base_payload["results_truncated"] = True
                base_payload["total_results"] = len(results)

        # Global webhooks from mapo.yaml
        if webhook_manager and config.webhooks.enabled:
            payload = {**base_payload}
            webhook_manager.send_webhook(event_type, payload)

        # Per-job webhook URL (set in UI, no yaml needed)
        job_webhook_url = params.get("webhook_url", "")
        if job_webhook_url:
            _send_job_webhook(job_webhook_url, params.get("webhook_headers", {}),
                              event_type, base_payload)

    except Exception as e:
        print(f"[Mapo] Webhook failed: {e}")


async def _send_job_webhook_async(url: str, headers: dict, event_type: str, payload: dict):
    """Async webhook delivery — runs as a background task."""
    body = {"event": event_type, "data": payload}
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, content=json.dumps(body, default=str), headers=req_headers)
            resp.raise_for_status()
        print(f"[Mapo] Job webhook delivered to {url}")
    except Exception as e:
        print(f"[Mapo] Job webhook to {url} failed: {e}")


def _send_job_webhook(url: str, headers: dict, event_type: str, payload: dict):
    """Schedule async webhook delivery (fire and forget).

    Falls back to a thread if called from a sync context with no event loop.
    """
    try:
        asyncio.create_task(_send_job_webhook_async(url, headers, event_type, payload))
    except RuntimeError:
        import threading
        threading.Thread(
            target=lambda: asyncio.run(
                _send_job_webhook_async(url, headers, event_type, payload)
            ),
            daemon=True,
        ).start()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(job_id: str, params: dict):
    """Execute the full scrape -> enrich -> reviews pipeline for a job.

    Retries up to ``max_retries`` times on failure (default 2, so 3 total
    attempts).  Each retry waits ``retry_delay * attempt`` seconds.
    Partial results from earlier attempts are preserved.
    """
    max_retries = params.get("max_retries", 2)
    retry_delay = params.get("retry_delay", 30)

    for attempt in range(max_retries + 1):
        success = await _run_pipeline_attempt(job_id, params, attempt, max_retries, retry_delay)
        if success:
            return
        # If not the last attempt, wait and retry
        if attempt < max_retries:
            wait = retry_delay * (attempt + 1)
            job = _jobs[job_id]
            job["status"] = "retrying"
            job["error"] = f"Attempt {attempt + 1} failed, retrying in {wait}s..."
            job["updated_at"] = time.time()
            _save_job(job_id)
            await _broadcast(job_id, {
                "type": "retrying",
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "retry_in": wait,
            })
            await asyncio.sleep(wait)


async def _run_pipeline_attempt(job_id: str, params: dict,
                                 attempt: int, max_retries: int,
                                 retry_delay: int) -> bool:
    """Single pipeline attempt. Returns True on success, False on retryable failure."""
    job = _jobs[job_id]
    progress = JobProgress()
    job["progress"] = progress
    job["status"] = "running"
    job["updated_at"] = time.time()
    _save_job(job_id)

    if attempt > 0:
        await _broadcast(job_id, {
            "type": "progress",
            "message": f"Retry attempt {attempt + 1}/{max_retries + 1}",
            **progress.to_dict(),
        })

    try:
        # -- build query list -----------------------------------------------
        queries_raw = [q.strip() for q in params.get("query", "").split("\n") if q.strip()]
        task_data = {
            "queries": queries_raw,
            "country": params.get("country", ""),
            "business_type": params.get("business_type", ""),
            "state": params.get("state", ""),
            "max_results": params.get("max_results", 100),
            "lang": params.get("lang", ""),
            "coordinates": params.get("coordinates", ""),
            "zoom_level": params.get("zoom_level", 14),
            "radius_meters": params.get("radius_meters"),
            "randomize_cities": params.get("randomize_cities", True),
            "max_cities": params.get("max_cities"),
        }

        sub_tasks = split_task_by_query(task_data)
        progress.total_queries = len(sub_tasks)

        prog_dict = progress.to_dict()
        await _broadcast(job_id, {"type": "progress", **prog_dict})

        # -- scrape places --------------------------------------------------
        # If target_new is set, scrape extra to compensate for cross-ref dedup losses
        target_new = params.get("target_new")
        target_buffer = params.get("target_buffer") or 2.0
        original_max = params.get("max_results", 100)
        if target_new and (params.get("skip_existing_csv") or params.get("skip_existing_csv_data")):
            buffered_max = min(int(target_new * target_buffer), config.limits.max_results_per_query)
            print(f"[Mapo] target_new={target_new}, scraping {buffered_max} per query (buffer x{target_buffer})")
        else:
            buffered_max = original_max

        all_places: list[dict] = []
        for st in sub_tasks:
            place_data = {
                "query": st.get("query", ""),
                "max": buffered_max,
                "lang": st.get("lang", ""),
                "geo_coordinates": st.get("coordinates", ""),
                "zoom": st.get("zoom_level", 14),
                "radius_meters": st.get("radius_meters"),
                "links": st.get("links"),
            }

            places_obj = await scrape_places(place_data)

            if places_obj is not None:
                places = places_obj.get("places", [])
                for p in places:
                    p["query"] = st.get("query", "")
                all_places.extend(places)
                progress.total_places_found = len(all_places)

            progress.completed_queries += 1
            progress.places_scraped = len(all_places)
            job["results"] = all_places
            job["updated_at"] = time.time()
            # Throttle DB saves: every 10 queries OR final query (avoids blocking the loop)
            if progress.completed_queries % 10 == 0 or progress.completed_queries == len(sub_tasks):
                _save_job(job_id)
            prog_dict = progress.to_dict()
            await _broadcast(job_id, {"type": "progress", **prog_dict})

        # -- apply server-side filters (before enrichment to save API calls) --
        filter_criteria = {}
        for key in ("has_website", "min_reviews", "min_rating", "max_rating",
                     "has_phone", "skip_closed", "category_in", "price_range"):
            val = params.get(key)
            if val is not None and val != "" and val is not False:
                filter_criteria[key] = val
        if params.get("skip_closed"):
            filter_criteria["skip_closed"] = True
        if filter_criteria:
            all_places = filter_places(all_places, filter_criteria)

        # -- cross-reference dedup (skip places already in user's CSV) -----
        skip_csv = params.get("skip_existing_csv") or ""
        skip_data = params.get("skip_existing_csv_data") or ""
        if skip_csv or skip_data:
            try:
                from backend.scrapers.filters import load_existing_keys, filter_against_existing
                dedup_field = params.get("skip_existing_field") or "place_id"
                if skip_data:
                    existing = load_existing_keys(skip_data, dedup_field, is_data=True)
                else:
                    existing = load_existing_keys(skip_csv, dedup_field, is_data=False)
                before = len(all_places)
                all_places = filter_against_existing(all_places, existing, dedup_field)
                print(f"[Mapo] Cross-ref ({dedup_field}): {len(all_places)} new, {before - len(all_places)} skipped")
            except Exception as e:
                print(f"[Mapo] Cross-ref failed: {e}")

        # -- trim to target_new (top-up mode) -----------------------------
        if target_new:
            if len(all_places) >= target_new:
                all_places = all_places[:target_new]
                print(f"[Mapo] Trimmed to target_new={target_new}")
            else:
                print(f"[Mapo] WARNING: target_new={target_new} but only {len(all_places)} new places found (Google ran out)")

        # -- social enrichment ----------------------------------------------
        api_key = params.get("enrichment_api_key", "")
        should_scrape_socials = bool(api_key)

        if should_scrape_socials:
            social_input = [
                {"place_id": p["place_id"], "website": p["website"], "key": api_key}
                for p in all_places if p.get("website")
            ]
            raw_social = await scrape_social(social_input)
            social_results = remove_nones(raw_social) if raw_social else []
        else:
            social_results = []

        all_places = _merge_social_data(all_places, social_results, should_scrape_socials)

        # -- email quality analysis -----------------------------------------
        for place in all_places:
            emails = place.get("emails", [])
            if emails and isinstance(emails, list) and emails[0] and "@" in str(emails[0]):
                analysis = analyze_emails(emails)
                place["best_email"] = analysis["best_email"]
                place["best_email_type"] = analysis["best_type"]
                place["best_email_score"] = analysis["best_score"]
                place["email_recommendation"] = analysis["recommendation"]
            else:
                place["best_email"] = None
                place["best_email_type"] = None
                place["best_email_score"] = 0
                place["email_recommendation"] = "No email found. Try cold calling."

        # -- AI email ranking (only if AI enabled and place has 2+ emails) ---
        if config.ai.enabled and config.ai.api_key:
            try:
                from backend.ai.lead_scoring import rank_emails_with_ai
                for place in all_places:
                    emails = place.get("emails", [])
                    if isinstance(emails, list) and len([e for e in emails if e and "@" in str(e)]) >= 2:
                        ranked = rank_emails_with_ai(
                            emails=emails,
                            place=place,
                            icp=config.ai.icp,
                            product_description=config.ai.product_description,
                        )
                        if ranked:
                            place["best_email_ai"] = ranked.get("best_email")
                            place["best_email_ai_reasoning"] = ranked.get("best_email_reasoning")
                            place["ranked_emails"] = ranked.get("ranked_emails")
            except Exception as e:
                print(f"[Mapo] AI email ranking failed: {e}")

        # -- reviews --------------------------------------------------------
        if params.get("enable_reviews"):
            max_rev = params.get("max_reviews", 20)
            lang = params.get("lang", "") or "en"
            reviews_input = [
                {
                    "place_id": p["place_id"],
                    "link": p["link"],
                    "max": min(max_rev, p["reviews"]) if max_rev else p["reviews"],
                    "reviews_sort": params.get("reviews_sort", "newest"),
                    "lang": lang,
                }
                for p in all_places if p.get("reviews", 0) >= 1
            ]
            review_results = await scrape_reviews(reviews_input)
        else:
            review_results = []

        all_places = _merge_reviews(all_places, review_results)

        # -- order fields ---------------------------------------------------
        social_keys = SOCIAL_MEDIA_KEYS if api_key else []
        all_fields = [f for f in OUTPUT_FIELDS if f not in SOCIAL_MEDIA_KEYS or f in social_keys]
        results = [sort_dict_by_keys(p, all_fields) for p in all_places]

        # -- apply field selection (export presets / custom fields) -------
        export_fields = resolve_export_fields(
            preset=params.get("export_preset", ""),
            fields=params.get("export_fields"),
        )
        if export_fields:
            results = select_fields(results, export_fields)
            print(f"[Mapo] Field selection: {len(export_fields)} fields per place")

        # -- finalize -------------------------------------------------------
        job["results"] = results
        job["status"] = "completed"
        job["updated_at"] = time.time()
        _save_job(job_id)

        # Auto-export CSV to data/exports/
        _auto_export(job_id, results)

        # Fire webhook if configured
        _fire_webhook(job_id, "task.completed", len(results), results=results)

        await _broadcast(job_id, {
            "type": "completed",
            "total_results": len(results),
            **progress.to_dict(),
        })
        return True  # success

    except asyncio.CancelledError:
        job["status"] = "cancelled"
        job["updated_at"] = time.time()
        _save_job(job_id)
        await _broadcast(job_id, {"type": "cancelled"})
        return True  # don't retry cancelled jobs

    except Exception as exc:
        is_last_attempt = attempt >= max_retries
        print(f"[Mapo] Pipeline attempt {attempt + 1}/{max_retries + 1} failed: {exc}")

        if is_last_attempt:
            # Final failure — update status and fire error webhooks
            job["status"] = "failed"
            job["error"] = str(exc)
            job["updated_at"] = time.time()
            _save_job(job_id)
            _fire_webhook(job_id, "task.failed", len(job.get("results", [])))
            # Fire error webhooks (per-job + global from settings)
            error_payload = {
                "job_id": job_id,
                "query": params.get("query", ""),
                "error": str(exc),
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "results_before_failure": len(job.get("results", [])),
                "timestamp": time.time(),
            }
            error_url = params.get("error_webhook_url", "")
            global_error_url = _load_ui_settings().get("webhooks", {}).get("error_url", "")

            # Send formatted notification (auto-detects Slack/Discord/ntfy/etc.)
            if error_url:
                await send_notification_async(
                    url=error_url,
                    title="Mapo Job Failed",
                    message=f"Query: {params.get('query', 'N/A')[:100]}\nError: {str(exc)[:200]}",
                    level="error",
                    extra={
                        "job_id": job_id[:8],
                        "attempt": attempt + 1,
                        "results_before_failure": len(job.get("results", [])),
                    },
                )
            if global_error_url and global_error_url != error_url:
                await send_notification_async(
                    url=global_error_url,
                    title="Mapo Job Failed",
                    message=f"Query: {params.get('query', 'N/A')[:100]}\nError: {str(exc)[:200]}",
                    level="error",
                    extra={
                        "job_id": job_id[:8],
                        "attempt": attempt + 1,
                        "results_before_failure": len(job.get("results", [])),
                    },
                )
            # Auto-export whatever we got before failure
            if job.get("results"):
                _auto_export(job_id, job["results"])
            await _broadcast(job_id, {"type": "error", "error": str(exc)})
            return True  # done (failed), don't retry
        else:
            # Retryable failure — preserve partial results, will retry
            job["error"] = f"Attempt {attempt + 1} failed: {exc}"
            job["updated_at"] = time.time()
            _save_job(job_id)
            return False  # signal retry


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    os.makedirs("data", exist_ok=True)
    _init_db()
    _load_jobs()
    _detect_unclean_shutdown()
    asyncio.create_task(_heartbeat_loop())


# ---------------------------------------------------------------------------
# Crash detection + heartbeat
# ---------------------------------------------------------------------------

_STARTUP_FLAG = os.path.join("data", ".running")
_STARTUP_TIME = time.time()


def _detect_unclean_shutdown():
    """If a .running flag exists from a previous run, the previous instance crashed."""
    if os.path.exists(_STARTUP_FLAG):
        try:
            with open(_STARTUP_FLAG) as f:
                last_pid = f.read().strip()
            print(f"[Mapo] WARNING: detected unclean shutdown (previous pid={last_pid})")
            # Fire crash notification to heartbeat URL if configured
            if config.webhooks.heartbeat_url:
                _send_crash_notification(last_pid)
        except Exception:
            pass

    # Write current pid for next startup
    try:
        with open(_STARTUP_FLAG, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def _get_notification_url() -> str:
    """Resolve which URL to use for notifications (heartbeat URL or fallback to error webhook)."""
    url = config.webhooks.heartbeat_url
    if not url:
        url = _load_ui_settings().get("webhooks", {}).get("error_url", "")
    return url


def _send_crash_notification(last_pid: str):
    """Notify about a previous unclean shutdown via any supported provider."""
    url = _get_notification_url()
    if not url:
        return
    import threading

    def _send():
        send_notification(
            url=url,
            title="Mapo Crashed",
            message=f"Mapo restarted after an unclean shutdown. Previous PID: {last_pid}",
            level="error",
            extra={
                "previous_pid": last_pid,
                "recovered_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "host": os.environ.get("HOSTNAME", "unknown"),
            },
        )

    threading.Thread(target=_send, daemon=True).start()


async def _heartbeat_loop():
    """Background task: send heartbeat to configured URL on interval (any provider)."""
    await asyncio.sleep(5)  # let startup finish
    while True:
        url = _get_notification_url()
        interval = max(30, config.webhooks.heartbeat_interval)
        if url and config.webhooks.heartbeat_interval > 0:
            running_jobs = sum(1 for j in _jobs.values() if j.get("status") in ("running", "retrying"))
            failed_recent = sum(
                1 for j in _jobs.values()
                if j.get("status") == "failed" and (time.time() - j.get("updated_at", 0)) < interval * 2
            )
            level = "warning" if failed_recent > 0 else "info"
            await send_notification_async(
                url=url,
                title="Mapo Heartbeat",
                message=f"Alive — {running_jobs} job(s) running, uptime {int((time.time() - _STARTUP_TIME) / 60)}min",
                level=level,
                extra={
                    "uptime_minutes": int((time.time() - _STARTUP_TIME) / 60),
                    "total_jobs": len(_jobs),
                    "running_jobs": running_jobs,
                    "failed_recent": failed_recent,
                    "pid": os.getpid(),
                },
            )
        await asyncio.sleep(interval)


@app.on_event("shutdown")
async def shutdown():
    """Clean shutdown — remove the .running flag."""
    try:
        if os.path.exists(_STARTUP_FLAG):
            os.remove(_STARTUP_FLAG)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/v1/scrape")
async def start_scrape(req: ScrapeRequest):
    if not req.query and not req.country:
        return JSONResponse(
            status_code=422,
            content={"detail": "Either 'query' or 'country' + 'business_type' is required."},
        )

    # ---- Enforce hard limits ----
    limits = config.limits

    if req.max_results > limits.max_results_per_query:
        return JSONResponse(
            status_code=422,
            content={"detail": f"max_results ({req.max_results}) exceeds limit of {limits.max_results_per_query}. Adjust in Settings."},
        )

    if req.max_cities and req.max_cities > limits.max_cities_per_job:
        return JSONResponse(
            status_code=422,
            content={"detail": f"max_cities ({req.max_cities}) exceeds limit of {limits.max_cities_per_job}."},
        )

    estimated_total = req.max_results * (req.max_cities or 1)
    if estimated_total > limits.max_total_places:
        return JSONResponse(
            status_code=422,
            content={"detail": f"Estimated total places ({estimated_total}) exceeds limit of {limits.max_total_places}. Reduce max_results or max_cities."},
        )

    # Check concurrent job count
    running = sum(1 for j in _jobs.values() if j.get("status") in ("running", "retrying", "created"))
    if running >= limits.max_concurrent_jobs:
        return JSONResponse(
            status_code=429,
            content={"detail": f"Too many concurrent jobs ({running}/{limits.max_concurrent_jobs}). Wait for one to finish."},
        )

    job_id = str(uuid.uuid4())
    now = time.time()
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "created",
        "params": req.model_dump(),
        "results": [],
        "error": None,
        "created_at": now,
        "updated_at": now,
        "progress": None,
        "_task": None,
    }
    _save_job(job_id)

    task = asyncio.create_task(run_pipeline(job_id, req.model_dump()))
    _jobs[job_id]["_task"] = task

    # Schedule auto-cancel after max_runtime_minutes
    asyncio.create_task(_runtime_watcher(job_id, limits.max_runtime_minutes))

    return {"job_id": job_id, "status": "created"}


async def _runtime_watcher(job_id: str, max_minutes: int):
    """Cancel a job that runs longer than max_minutes."""
    await asyncio.sleep(max_minutes * 60)
    job = _jobs.get(job_id)
    if not job:
        return
    if job["status"] in ("running", "retrying", "created"):
        task = job.get("_task")
        if task and not task.done():
            print(f"[Mapo] Auto-cancelling {job_id[:8]} (exceeded {max_minutes}min runtime)")
            task.cancel()
            job["status"] = "cancelled"
            job["error"] = f"Auto-cancelled after {max_minutes} minute runtime limit"
            job["updated_at"] = time.time()
            _save_job(job_id)


@app.get("/api/v1/jobs")
async def list_jobs():
    summaries = []
    for j in _jobs.values():
        summaries.append({
            "job_id": j["job_id"],
            "status": j["status"],
            "created_at": j.get("created_at"),
            "updated_at": j.get("updated_at"),
            "total_results": len(j.get("results") or []),
            "error": j.get("error"),
            "progress": j["progress"].to_dict() if j.get("progress") else None,
        })
    return summaries


@app.get("/api/v1/jobs/{job_id}")
async def get_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"detail": "Job not found."})
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "params": job.get("params"),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "total_results": len(job.get("results") or []),
        "results": job.get("results", []),
        "progress": job["progress"].to_dict() if job.get("progress") else None,
    }


@app.get("/api/v1/jobs/{job_id}/download")
async def download_job(job_id: str, format: str = "csv"):
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"detail": "Job not found."})

    results = job.get("results", [])
    if not results:
        return JSONResponse(status_code=404, content={"detail": "No results to download."})

    if format == "json":
        return JSONResponse(
            content=results,
            headers={"Content-Disposition": f"attachment; filename=mapo_{job_id}.json"},
        )

    # CSV
    buf = io.StringIO()
    fieldnames = list(results[0].keys())
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in results:
        writer.writerow(_flatten_for_csv(row))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=mapo_{job_id}.csv"},
    )


@app.delete("/api/v1/jobs/{job_id}")
async def cancel_job(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"detail": "Job not found."})

    task = job.get("_task")
    if task and not task.done():
        task.cancel()

    job["status"] = "cancelled"
    job["updated_at"] = time.time()
    _save_job(job_id)
    return {"job_id": job_id, "status": "cancelled"}


@app.post("/api/v1/enrich")
async def enrich(req: EnrichRequest):
    """Standalone website enrichment endpoint."""
    items = await asyncio.to_thread(
        get_website_contacts, req.websites, metadata=req.api_key
    )
    output: list[dict] = []
    for i, item in enumerate(items or []):
        website = req.websites[i] if i < len(req.websites) else ""
        if item and item.get("error"):
            output.append({"website": website, **make_empty_social(item["error"])})
        elif item and item.get("data"):
            output.append({"website": website, **item["data"]})
        else:
            output.append({"website": website, **make_empty_social("Failed")})
    return output


@app.websocket("/api/v1/ws/{job_id}")
async def ws_progress(ws: WebSocket, job_id: str):
    await ws.accept()
    _ws_clients.setdefault(job_id, []).append(ws)

    # Send current state immediately
    job = _jobs.get(job_id)
    if job:
        await ws.send_json({
            "type": "status",
            "status": job["status"],
            "progress": job["progress"].to_dict() if job.get("progress") else None,
        })

    try:
        while True:
            # Keep connection alive; client can send pings
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients = _ws_clients.get(job_id, [])
        if ws in clients:
            clients.remove(ws)


# ---------------------------------------------------------------------------
# SSE progress endpoint (replaces WebSocket for one-way streaming)
# ---------------------------------------------------------------------------

@app.get("/api/v1/progress/{job_id}")
async def sse_progress(job_id: str):
    """Server-Sent Events stream for real-time job progress."""
    async def generate():
        job = _jobs.get(job_id)
        if job is None:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Job not found'})}\n\n"
            return

        # Send current state immediately
        yield f"data: {json.dumps({'type': 'status', 'status': job['status'], 'progress': job['progress'].to_dict() if job.get('progress') else None})}\n\n"

        # If already done, close
        if job["status"] in ("completed", "failed", "cancelled"):
            yield f"data: {json.dumps({'type': job['status'], 'total_results': len(job.get('results', []))})}\n\n"
            return

        # Stream until done
        last_scraped = -1
        while True:
            job = _jobs.get(job_id)
            if job is None:
                break

            progress = job.get("progress")
            status = job["status"]

            if progress and progress.places_scraped != last_scraped:
                last_scraped = progress.places_scraped
                yield f"data: {json.dumps({'type': 'progress', **progress.to_dict()})}\n\n"

            if status == "completed":
                yield f"data: {json.dumps({'type': 'completed', 'total_results': len(job.get('results', []))})}\n\n"
                break
            elif status == "failed":
                yield f"data: {json.dumps({'type': 'error', 'error': job.get('error', 'Unknown')})}\n\n"
                break
            elif status == "cancelled":
                yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------
# Data endpoints (countries, states, categories)
# ---------------------------------------------------------------------------

@app.get("/api/v1/countries")
async def list_countries():
    """Return all countries with city counts for the dropdown."""
    from backend.data.countries import country_code_to_cities
    result = []
    for code, cities in sorted(country_code_to_cities.items()):
        count = len(cities)
        result.append({"value": code, "cities": count})
    return result


@app.get("/api/v1/states")
async def list_states(country: str = "US"):
    """Return states/regions for a country."""
    states = get_states(country)
    return {"states": states}


@app.get("/api/v1/states/{state}/cities")
async def list_state_cities(state: str, country: str = "US"):
    """Return cities for a given state."""
    cities = get_state_cities(country, state)
    return {"cities": cities}


@app.get("/api/v1/categories")
async def list_categories():
    """Return business category options for the dropdown."""
    from backend.data.categories import category_options
    return category_options


@app.get("/api/v1/export-presets")
async def list_export_presets():
    """Return all export preset definitions (name → field list)."""
    return EXPORT_PRESETS


@app.post("/api/v1/test-notification")
async def test_notification(request: Request):
    """Send a test notification to a URL — verify your Slack/Discord/ntfy/etc. setup."""
    body = await request.json()
    url = body.get("url", "")
    if not url:
        return JSONResponse(status_code=422, content={"detail": "url is required"})

    provider = detect_provider(url)
    success = await send_notification_async(
        url=url,
        title="Mapo Test Notification",
        message="This is a test notification from Mapo. If you see this, your notification setup is working.",
        level="info",
        extra={"test": True, "provider": provider},
    )
    return {"success": success, "provider": provider}


@app.get("/api/v1/fields")
async def list_all_fields():
    """Return all 80+ available output fields."""
    return {"fields": OUTPUT_FIELDS}


# ---------------------------------------------------------------------------
# Settings API (persisted to data/settings.json, hot-reloads config)
# ---------------------------------------------------------------------------

@app.get("/api/v1/settings")
async def get_settings():
    """Return current UI-saved settings."""
    return _load_ui_settings()


@app.put("/api/v1/settings")
async def save_settings(request: Request):
    """Save settings from UI and hot-reload config."""
    body = await request.json()
    _save_ui_settings(body)
    reload_config()
    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Schedules API (cron jobs managed via UI)
# ---------------------------------------------------------------------------

@app.get("/api/v1/schedules")
async def list_schedules():
    from backend.scheduler import load_schedules
    return load_schedules()


@app.post("/api/v1/schedules")
async def create_schedule(request: Request):
    from backend.scheduler import load_schedules, save_schedules, scheduler as _sch
    body = await request.json()

    if not body.get("name") or not body.get("cron"):
        return JSONResponse(status_code=422, content={"detail": "name and cron are required"})

    schedules = load_schedules()
    new_sch = {
        "id": str(uuid.uuid4()),
        "name": body["name"],
        "cron": body["cron"],
        "enabled": body.get("enabled", True),
        "params": body.get("params", {}),
        "created_at": time.time(),
        "last_run": None,
        "last_status": None,
    }
    schedules.append(new_sch)
    save_schedules(schedules)

    try:
        _sch.reload_schedules()
    except Exception as e:
        print(f"[Mapo] Failed to reload schedules: {e}")

    return new_sch


@app.put("/api/v1/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, request: Request):
    from backend.scheduler import load_schedules, save_schedules, scheduler as _sch
    body = await request.json()

    schedules = load_schedules()
    for s in schedules:
        if s.get("id") == schedule_id:
            for key in ("name", "cron", "enabled", "params"):
                if key in body:
                    s[key] = body[key]
            save_schedules(schedules)
            try:
                _sch.reload_schedules()
            except Exception as e:
                print(f"[Mapo] Failed to reload schedules: {e}")
            return s

    return JSONResponse(status_code=404, content={"detail": "Schedule not found"})


@app.delete("/api/v1/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str):
    from backend.scheduler import load_schedules, save_schedules, scheduler as _sch

    schedules = load_schedules()
    schedules = [s for s in schedules if s.get("id") != schedule_id]
    save_schedules(schedules)
    try:
        _sch.reload_schedules()
    except Exception as e:
        print(f"[Mapo] Failed to reload schedules: {e}")
    return {"status": "deleted"}


@app.post("/api/v1/schedules/{schedule_id}/run")
async def run_schedule_now(schedule_id: str):
    """Manually trigger a schedule to run immediately."""
    from backend.scheduler import load_schedules

    schedules = load_schedules()
    sch = next((s for s in schedules if s.get("id") == schedule_id), None)
    if not sch:
        return JSONResponse(status_code=404, content={"detail": "Schedule not found"})

    # Run as a normal scrape job
    params = sch.get("params", {})
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
    task = asyncio.create_task(run_pipeline(job_id, params))
    _jobs[job_id]["_task"] = task
    return {"job_id": job_id, "schedule_id": schedule_id}


# ---------------------------------------------------------------------------
# Static frontend (optional)
# ---------------------------------------------------------------------------

try:
    app.mount("/", StaticFiles(directory="frontend", html=True))
except Exception:
    pass
