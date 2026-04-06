"""
Social media contact scraper.

Uses the pluggable enrichment system to get social media profiles, emails,
and phone numbers for business websites found on Google Maps.
"""
import asyncio
import traceback

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
            return {"data": None, "error": FAILED_DUE_TO_CREDITS_EXHAUSTED}
        if "not subscribed" in error_msg.lower():
            return {"data": None, "error": FAILED_DUE_TO_NOT_SUBSCRIBED}

        return {"data": None, "error": FAILED_DUE_TO_UNKNOWN_ERROR}


def get_website_contacts(website, api_key):
    """Fetch social/contact info for a single website URL (sync)."""
    return _enrich_website(website, api_key)


def scrape_social_one(data):
    """Fetch social details for a place and tag with place_id (sync)."""
    result = get_website_contacts(data["website"], data["key"])
    result["place_id"] = data["place_id"]
    return result


async def scrape_social(data_list):
    """
    Enrich multiple places with social data in parallel.

    Uses asyncio.to_thread with a semaphore limiting to 5 concurrent workers.
    """
    sem = asyncio.Semaphore(5)

    async def fetch(data):
        async with sem:
            return await asyncio.to_thread(scrape_social_one, data)

    tasks = [fetch(d) for d in data_list]
    return await asyncio.gather(*tasks)


def make_empty_social(msg=None):
    """Create an empty social data dict, optionally with an error message."""
    return {
        "emails": [msg] if msg else [],
        "phones": [msg] if msg else [],
        **{field: msg for field in SOCIAL_FIELDS if field not in ("emails", "phones")},
    }
