"""
Request validation and response helpers for the Mapo REST API.

Simple dict-based validators — no heavy ORM or schema library required.
"""


VALID_REVIEW_SORTS = {"newest", "most_relevant", "highest_rating", "lowest_rating"}
VALID_ENRICH_PROVIDERS = {"hunter", "rapidapi", "apollo"}


def validate_scrape_request(data):
    """
    Validate a scrape request payload.

    Returns:
        (cleaned_data, errors) — *errors* is a list of strings; empty means valid.
    """
    if not isinstance(data, dict):
        return None, ["Request body must be a JSON object."]

    errors = []

    query = data.get("query")
    country = data.get("country")
    business_type = data.get("business_type")

    if not query and not (country and business_type):
        errors.append(
            "Either 'query' or both 'country' and 'business_type' are required."
        )

    max_results = data.get("max_results")
    if max_results is not None:
        try:
            max_results = int(max_results)
            if max_results < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("'max_results' must be a positive integer.")

    zoom_level = data.get("zoom_level")
    if zoom_level is not None:
        try:
            zoom_level = float(zoom_level)
            if not (1 <= zoom_level <= 21):
                raise ValueError
        except (TypeError, ValueError):
            errors.append("'zoom_level' must be a number between 1 and 21.")

    if errors:
        return None, errors

    cleaned = {
        "query": query or "",
        "max_results": max_results or 100,
        "lang": data.get("lang", ""),
        "coordinates": data.get("coordinates", ""),
        "zoom_level": zoom_level or 14,
        "country": country or "",
        "business_type": business_type or "",
        "enable_reviews": bool(data.get("enable_reviews", False)),
        "enrichment_api_key": data.get("enrichment_api_key", ""),
    }
    return cleaned, []


def validate_enrich_request(data):
    """
    Validate an enrichment request payload.

    Returns:
        (cleaned_data, errors)
    """
    if not isinstance(data, dict):
        return None, ["Request body must be a JSON object."]

    errors = []

    websites = data.get("websites")
    if not isinstance(websites, list) or len(websites) == 0:
        errors.append("'websites' must be a non-empty list of URLs.")
    elif not all(isinstance(w, str) and w.strip() for w in websites):
        errors.append("Each entry in 'websites' must be a non-empty string.")

    provider = data.get("provider", "rapidapi")
    if provider not in VALID_ENRICH_PROVIDERS:
        errors.append(
            f"'provider' must be one of: {', '.join(sorted(VALID_ENRICH_PROVIDERS))}."
        )

    if errors:
        return None, errors

    cleaned = {
        "websites": [w.strip() for w in websites],
        "provider": provider,
    }
    return cleaned, []


def error_response(message, status_code=400):
    """
    Build a standard error dict.

    The caller is responsible for setting ``response.status`` on the Bottle
    response object; this helper just returns the JSON-serialisable dict.
    """
    return {
        "error": True,
        "status_code": status_code,
        "message": message,
    }
