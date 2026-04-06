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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
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
from backend.utils import remove_nones, extract_path
from backend.progress import JobProgress

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="Mapo")

# ---------------------------------------------------------------------------
# Job store
# ---------------------------------------------------------------------------

_jobs: dict = {}
_ws_clients: dict[str, list[WebSocket]] = {}
_DB_PATH = os.path.join(".", "data", "mapo_jobs.db")


def _init_db():
    """Create the jobs table if it does not exist."""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
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
    conn = sqlite3.connect(_DB_PATH)
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
    conn = sqlite3.connect(_DB_PATH)
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
    "technologies", "cms", "ad_pixels", "has_contact_form", "form_provider",
]

OUTPUT_FIELDS = [
    "place_id", "name", "description", "is_spending_on_ads", "reviews",
    "competitors", "website", "can_claim",
] + SOCIAL_MEDIA_KEYS + [
    "owner", "featured_image", "main_category", "categories", "rating",
    "workday_timing", "is_temporarily_closed", "is_permanently_closed",
    "closed_on", "phone", "address", "review_keywords", "link", "status",
    "price_range", "reviews_per_rating", "featured_question", "reviews_link",
    "coordinates", "plus_code", "detailed_address", "time_zone", "cid",
    "data_id", "about", "images", "hours", "most_popular_times",
    "popular_times", "menu", "reservations", "order_online_links",
] + DETECTION_KEYS + [
    "lead_score", "pitch_summary",
    "review_sentiment", "review_themes",
    "featured_reviews", "detailed_reviews", "query",
]


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class ScrapeRequest(BaseModel):
    query: str = ""
    country: str = ""
    state: str = ""
    business_type: str = ""
    max_results: int = 100
    lang: str = ""
    coordinates: str = ""
    zoom_level: float = 14
    enable_reviews: bool = False
    max_reviews: int = 20
    reviews_sort: str = "newest"
    enrichment_api_key: str = ""
    enable_ai: bool = False


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
# Pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(job_id: str, params: dict):
    """Execute the full scrape -> enrich -> reviews pipeline for a job."""
    job = _jobs[job_id]
    progress = JobProgress()
    job["progress"] = progress
    job["status"] = "running"
    job["updated_at"] = time.time()
    _save_job(job_id)

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
            "randomize_cities": False,
            "max_cities": None,
        }

        sub_tasks = split_task_by_query(task_data)
        progress.total_queries = len(sub_tasks)

        await _broadcast(job_id, {"type": "progress", **progress.to_dict()})

        # -- scrape places --------------------------------------------------
        all_places: list[dict] = []
        for st in sub_tasks:
            place_data = {
                "query": st.get("query", ""),
                "max": st.get("max_results", 100),
                "lang": st.get("lang", ""),
                "geo_coordinates": st.get("coordinates", ""),
                "zoom": st.get("zoom_level", 14),
                "links": st.get("links"),
            }

            places_obj = await asyncio.to_thread(scrape_places, place_data)

            if places_obj is not None:
                places = places_obj.get("places", [])
                for p in places:
                    p["query"] = st.get("query", "")
                all_places.extend(places)
                progress.total_places_found = len(all_places)

            progress.completed_queries += 1
            progress.places_scraped = len(all_places)
            job["updated_at"] = time.time()
            await _broadcast(job_id, {"type": "progress", **progress.to_dict()})

        # -- social enrichment ----------------------------------------------
        api_key = params.get("enrichment_api_key", "")
        should_scrape_socials = bool(api_key)

        if should_scrape_socials:
            social_input = [
                {"place_id": p["place_id"], "website": p["website"], "key": api_key}
                for p in all_places if p.get("website")
            ]
            raw_social = await asyncio.to_thread(scrape_social, social_input)
            social_results = remove_nones(raw_social) if raw_social else []
        else:
            social_results = []

        all_places = _merge_social_data(all_places, social_results, should_scrape_socials)

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
            review_results = await asyncio.to_thread(scrape_reviews, reviews_input)
        else:
            review_results = []

        all_places = _merge_reviews(all_places, review_results)

        # -- order fields ---------------------------------------------------
        social_keys = SOCIAL_MEDIA_KEYS if api_key else []
        all_fields = [f for f in OUTPUT_FIELDS if f not in SOCIAL_MEDIA_KEYS or f in social_keys]
        results = [sort_dict_by_keys(p, all_fields) for p in all_places]

        # -- finalize -------------------------------------------------------
        job["results"] = results
        job["status"] = "completed"
        job["updated_at"] = time.time()
        _save_job(job_id)

        await _broadcast(job_id, {
            "type": "completed",
            "total_results": len(results),
            **progress.to_dict(),
        })

    except asyncio.CancelledError:
        job["status"] = "cancelled"
        job["updated_at"] = time.time()
        _save_job(job_id)
        await _broadcast(job_id, {"type": "cancelled"})

    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        job["updated_at"] = time.time()
        _save_job(job_id)
        await _broadcast(job_id, {"type": "error", "error": str(exc)})


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    os.makedirs("data", exist_ok=True)
    _init_db()
    _load_jobs()


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

    return {"job_id": job_id, "status": "created"}


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
        flat = {}
        for k, v in row.items():
            flat[k] = json.dumps(v) if isinstance(v, (list, dict)) else v
        writer.writerow(flat)

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
# Static frontend (optional)
# ---------------------------------------------------------------------------

try:
    app.mount("/", StaticFiles(directory="frontend", html=True))
except Exception:
    pass
