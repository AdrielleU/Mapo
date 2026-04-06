"""
RapidAPI Website Social Scraper enrichment provider.

Calls the Website Social Scraper API on RapidAPI to extract emails,
phone numbers, and social-media links from a given website.
"""
import logging
import time

import httpx

from backend.enrichment.base import EnrichmentProvider
from backend.config import config

logger = logging.getLogger(__name__)

RAPIDAPI_HOST = "website-social-scraper-api.p.rapidapi.com"
RAPIDAPI_URL = f"https://{RAPIDAPI_HOST}/contacts"

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def _get_proxy() -> str | None:
    """Return a proxy URL from the global ProxyManager, or None."""
    try:
        from backend.proxy import proxy_manager
        if proxy_manager.enabled:
            return proxy_manager.get_proxy()
    except Exception:
        pass
    return None


class RapidAPIProvider(EnrichmentProvider):
    """Enrichment via the RapidAPI Website Social Scraper."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.enrichment.api_key

    # -- internal helpers -------------------------------------------------

    def _build_client(self) -> httpx.Client:
        proxy = _get_proxy()
        return httpx.Client(proxy=proxy, timeout=30)

    def _headers(self) -> dict:
        return {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
        }

    def _request(self, website: str) -> dict:
        """Make the API call with retry logic for 429 / credit errors."""
        params = {"website": website}
        headers = self._headers()

        for attempt in range(1, MAX_RETRIES + 1):
            with self._build_client() as client:
                try:
                    resp = client.get(RAPIDAPI_URL, headers=headers, params=params)

                    if resp.status_code == 429:
                        logger.warning(
                            "RapidAPI rate-limited (429), retry %d/%d",
                            attempt,
                            MAX_RETRIES,
                        )
                        time.sleep(RETRY_DELAY)
                        continue

                    if resp.status_code == 403:
                        logger.error("RapidAPI subscription/credit error (403)")
                        return {}

                    if resp.status_code == 401:
                        logger.error("RapidAPI authentication error — check API key")
                        return {}

                    resp.raise_for_status()
                    return resp.json()

                except httpx.HTTPStatusError as exc:
                    logger.error("RapidAPI HTTP error: %s", exc)
                    return {}
                except httpx.RequestError as exc:
                    logger.error("RapidAPI request error: %s", exc)
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)
                        continue
                    return {}

        logger.error("RapidAPI: max retries exhausted for %s", website)
        return {}

    # -- public interface -------------------------------------------------

    def get_emails(self, website: str) -> list[str]:
        data = self._request(website)
        emails = data.get("emails", [])
        return list({e for e in emails if isinstance(e, str)})

    def get_social_links(self, website: str) -> dict:
        data = self._request(website)
        links: dict[str, str] = {}
        for key in ("facebook", "twitter", "instagram", "linkedin", "youtube", "tiktok", "github"):
            value = data.get(key)
            if value:
                links[key] = value
        return links

    def get_phone_info(self, website: str) -> list[str]:
        data = self._request(website)
        phones = data.get("phones", data.get("phone_numbers", []))
        return list({p for p in phones if isinstance(p, str)})

    def enrich(self, website: str) -> dict:
        """Single API call to get everything at once."""
        data = self._request(website)
        if not data:
            return {"emails": [], "social_links": {}, "phones": []}

        emails = list({e for e in data.get("emails", []) if isinstance(e, str)})
        phones = list(
            {p for p in data.get("phones", data.get("phone_numbers", [])) if isinstance(p, str)}
        )

        social_links: dict[str, str] = {}
        for key in ("facebook", "twitter", "instagram", "linkedin", "youtube", "tiktok", "github"):
            value = data.get(key)
            if value:
                social_links[key] = value

        return {
            "emails": emails,
            "social_links": social_links,
            "phones": phones,
        }
