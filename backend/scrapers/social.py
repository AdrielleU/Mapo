"""
Social media contact scraper.

Uses the pluggable enrichment system to get social media profiles, emails,
and phone numbers for business websites found on Google Maps.
"""
import traceback

from botasaurus.cache import DontCache
from botasaurus.task import task

FAILED_DUE_TO_CREDITS_EXHAUSTED = "FAILED_DUE_TO_CREDITS_EXHAUSTED"
FAILED_DUE_TO_NOT_SUBSCRIBED = "FAILED_DUE_TO_NOT_SUBSCRIBED"
FAILED_DUE_TO_UNKNOWN_ERROR = "FAILED_DUE_TO_UNKNOWN_ERROR"

SOCIAL_FIELDS = [
    "emails", "phones", "linkedin", "twitter", "facebook",
    "youtube", "instagram", "tiktok", "github", "snapchat", "pinterest",
]


def _enrich_website(website, api_key):
    """Call the configured enrichment provider for a website."""
    from backend.enrichment import get_provider

    try:
        provider = get_provider(api_key_override=api_key)
        result = provider.enrich(website)
        return {"data": result, "error": None}
    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()

        if "quota" in error_msg.lower() or "credit" in error_msg.lower():
            return DontCache({"data": None, "error": FAILED_DUE_TO_CREDITS_EXHAUSTED})
        if "not subscribed" in error_msg.lower():
            return DontCache({"data": None, "error": FAILED_DUE_TO_NOT_SUBSCRIBED})

        return DontCache({"data": None, "error": FAILED_DUE_TO_UNKNOWN_ERROR})


@task(
    close_on_crash=True,
    create_error_logs=False,
    output=None,
    parallel=5,
    cache=True,
)
def get_website_contacts(data, metadata):
    """Fetch social/contact info for a single website URL."""
    return _enrich_website(data, metadata)


@task(
    close_on_crash=True,
    create_error_logs=False,
    output=None,
    parallel=5,
)
def scrape_social(data):
    """Fetch social details for a place (by its website) and tag with place_id."""
    result = get_website_contacts(data["website"], metadata=data["key"])
    result["place_id"] = data["place_id"]
    return result


def make_empty_social(msg=None):
    """Create an empty social data dict, optionally with an error message."""
    return {
        "emails": [msg] if msg else [],
        "phones": [msg] if msg else [],
        **{field: msg for field in SOCIAL_FIELDS if field not in ("emails", "phones")},
    }
