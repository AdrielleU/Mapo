"""
Social media contact scraper.

Calls an external API to get social media profiles, emails, and phone numbers
for business websites found on Google Maps.
"""
import traceback
from time import sleep

import requests as http
from botasaurus.cache import DontCache
from botasaurus.task import task

FAILED_DUE_TO_CREDITS_EXHAUSTED = "FAILED_DUE_TO_CREDITS_EXHAUSTED"
FAILED_DUE_TO_NOT_SUBSCRIBED = "FAILED_DUE_TO_NOT_SUBSCRIBED"
FAILED_DUE_TO_UNKNOWN_ERROR = "FAILED_DUE_TO_UNKNOWN_ERROR"

API_URL = "https://website-social-scraper-api.p.rapidapi.com/contacts"
API_HOST = "website-social-scraper-api.p.rapidapi.com"

SOCIAL_FIELDS = [
    "emails", "phones", "linkedin", "twitter", "facebook",
    "youtube", "instagram", "tiktok", "github", "snapchat", "pinterest",
]


def _make_social_request(website, api_key, retry_count=3):
    """Call the social scraper API with retry logic for rate limiting."""
    if retry_count == 0:
        print(f"Failed to get social details for {website} after 3 retries")
        return DontCache(None)

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": API_HOST,
    }

    try:
        response = http.get(API_URL, headers=headers, params={"website": website})
        data = response.json()
    except Exception:
        traceback.print_exc()
        return DontCache({"data": None, "error": FAILED_DUE_TO_UNKNOWN_ERROR})

    if response.status_code == 200:
        if "pinterest" not in data:
            data["pinterest"] = None
        return {"data": data, "error": None}

    message = data.get("message", "")

    if "exceeded the MONTHLY quota" in message:
        return DontCache({"data": None, "error": FAILED_DUE_TO_CREDITS_EXHAUSTED})

    if "exceeded the rate limit" in message or "many requests" in message:
        sleep(2)
        return _make_social_request(website, api_key, retry_count - 1)

    if "You are not subscribed to this API." in message:
        return DontCache({"data": None, "error": FAILED_DUE_TO_NOT_SUBSCRIBED})

    print(f"Error: {response.status_code}", data)
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
    return _make_social_request(data, metadata)


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
