"""
REST API route definitions for Mapo.

All endpoints live under ``/api/v1/`` and return JSON.  They are registered
on a Bottle app via :func:`register_routes`.
"""
import json
import uuid
import time

from bottle import request, response, Bottle

from backend.api.models import (
    validate_scrape_request,
    validate_enrich_request,
    error_response,
)

# ---------------------------------------------------------------------------
# Lightweight in-process job store.
#
# In production the jobs come from botasaurus_server's internal database.
# We attempt to import its helpers; if unavailable we fall back to a simple
# in-memory dict so the API layer is always importable and testable.
# ---------------------------------------------------------------------------

_jobs: dict = {}

try:
    from botasaurus_server.server import Server as _Server  # noqa: F401
    _HAS_BOTASAURUS = True
except ImportError:
    _HAS_BOTASAURUS = False


def _json_response(data, status_code=200):
    """Serialise *data* to JSON and set the appropriate content type."""
    response.content_type = "application/json"
    response.status = status_code
    return json.dumps(data)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def health():
    """GET /api/v1/health"""
    return _json_response({"status": "ok", "version": "1.0.0"})


def create_scrape():
    """POST /api/v1/scrape — submit a new scraping job."""
    try:
        data = request.json
    except Exception:
        return _json_response(error_response("Invalid JSON body."), 400)

    if data is None:
        return _json_response(error_response("Request body is empty."), 400)

    cleaned, errors = validate_scrape_request(data)
    if errors:
        return _json_response(error_response("; ".join(errors)), 422)

    job_id = str(uuid.uuid4())

    # Try to dispatch through botasaurus_server if available
    if _HAS_BOTASAURUS:
        try:
            from botasaurus_server.task_routes import TaskRoutes
            task_data = {
                "query": cleaned["query"],
                "queries": [cleaned["query"]] if cleaned["query"] else [],
                "max_results": cleaned["max_results"],
                "lang": cleaned["lang"],
                "coordinates": cleaned["coordinates"],
                "zoom_level": cleaned["zoom_level"],
                "country": cleaned["country"],
                "business_type": cleaned["business_type"],
                "enable_reviews_extraction": cleaned["enable_reviews"],
                "api_key": cleaned["enrichment_api_key"],
            }
            result = TaskRoutes.create_task(
                scraper_name="google_maps_scraper",
                data=task_data,
            )
            if result and isinstance(result, dict):
                job_id = str(result.get("id", job_id))
        except Exception:
            # Fall back to in-memory tracking
            pass

    _jobs[job_id] = {
        "id": job_id,
        "status": "created",
        "params": cleaned,
        "results": [],
        "created_at": time.time(),
    }

    return _json_response({"job_id": job_id, "status": "created"}, 201)


def list_jobs():
    """GET /api/v1/jobs — paginated job listing."""
    try:
        page = int(request.params.get("page", 1))
        per_page = int(request.params.get("per_page", 20))
    except (TypeError, ValueError):
        return _json_response(error_response("'page' and 'per_page' must be integers."), 400)

    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 20

    all_jobs = list(_jobs.values())
    total = len(all_jobs)
    start = (page - 1) * per_page
    end = start + per_page
    page_jobs = all_jobs[start:end]

    return _json_response({"jobs": page_jobs, "total": total})


def get_job(job_id):
    """GET /api/v1/jobs/<job_id>"""
    job = _jobs.get(job_id)
    if job is None:
        return _json_response(error_response(f"Job '{job_id}' not found.", 404), 404)
    return _json_response({
        "id": job["id"],
        "status": job["status"],
        "results": job.get("results", []),
    })


def delete_job(job_id):
    """DELETE /api/v1/jobs/<job_id>"""
    if job_id not in _jobs:
        return _json_response(error_response(f"Job '{job_id}' not found.", 404), 404)
    del _jobs[job_id]
    return _json_response({"status": "deleted"})


def enrich():
    """POST /api/v1/enrich — run website enrichment directly."""
    try:
        data = request.json
    except Exception:
        return _json_response(error_response("Invalid JSON body."), 400)

    if data is None:
        return _json_response(error_response("Request body is empty."), 400)

    cleaned, errors = validate_enrich_request(data)
    if errors:
        return _json_response(error_response("; ".join(errors)), 422)

    try:
        from backend.scrapers.social import get_website_contacts

        results = get_website_contacts(
            cleaned["websites"],
            metadata=cleaned.get("api_key", ""),
        )
        enriched = []
        for i, item in enumerate(results or []):
            entry = {"website": cleaned["websites"][i]}
            if item and item.get("data"):
                entry.update(item["data"])
            elif item and item.get("error"):
                entry["error"] = item["error"]
            else:
                entry["error"] = "No data returned."
            enriched.append(entry)

        return _json_response({"results": enriched})

    except ImportError:
        return _json_response(
            error_response("Enrichment module is not available.", 501), 501
        )
    except Exception as exc:
        return _json_response(
            error_response(f"Enrichment failed: {exc}", 500), 500
        )


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_routes(app):
    """
    Mount all ``/api/v1/*`` routes on the given Bottle *app*.

    Parameters
    ----------
    app : bottle.Bottle
        The WSGI application to register routes on.
    """
    app.route("/api/v1/health", method="GET", callback=health)
    app.route("/api/v1/scrape", method="POST", callback=create_scrape)
    app.route("/api/v1/jobs", method="GET", callback=list_jobs)
    app.route("/api/v1/jobs/<job_id>", method="GET", callback=get_job)
    app.route("/api/v1/jobs/<job_id>", method="DELETE", callback=delete_job)
    app.route("/api/v1/enrich", method="POST", callback=enrich)
