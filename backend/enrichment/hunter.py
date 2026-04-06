"""
Hunter.io enrichment provider.

Uses the Hunter.io Domain Search API to find email addresses
associated with a given domain.  Hunter does not provide social
links or phone numbers, so those methods return empty results.
"""
import logging
from urllib.parse import urlparse

import httpx

from backend.enrichment.base import EnrichmentProvider
from backend.config import config

logger = logging.getLogger(__name__)

HUNTER_API_URL = "https://api.hunter.io/v2/domain-search"


def _get_proxy() -> str | None:
    try:
        from backend.proxy import proxy_manager
        if proxy_manager.enabled:
            return proxy_manager.get_proxy()
    except Exception:
        pass
    return None


def _extract_domain(website: str) -> str:
    """Normalise a website string into a bare domain."""
    if not website.startswith(("http://", "https://")):
        website = "https://" + website
    parsed = urlparse(website)
    domain = parsed.hostname or website
    # strip leading www.
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


class HunterIOProvider(EnrichmentProvider):
    """Enrichment via the Hunter.io Domain Search API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.enrichment.api_key

    def _build_client(self) -> httpx.Client:
        proxy = _get_proxy()
        return httpx.Client(proxy=proxy, timeout=30)

    def _request(self, website: str) -> dict:
        domain = _extract_domain(website)
        params = {"domain": domain, "api_key": self.api_key}

        with self._build_client() as client:
            try:
                resp = client.get(HUNTER_API_URL, params=params)

                if resp.status_code == 401:
                    logger.error("Hunter.io authentication error — check API key")
                    return {}
                if resp.status_code == 429:
                    logger.warning("Hunter.io rate-limited (429)")
                    return {}

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPStatusError as exc:
                logger.error("Hunter.io HTTP error: %s", exc)
                return {}
            except httpx.RequestError as exc:
                logger.error("Hunter.io request error: %s", exc)
                return {}

    # -- public interface -------------------------------------------------

    def get_emails(self, website: str) -> list[str]:
        data = self._request(website)
        emails_list = data.get("data", {}).get("emails", [])
        return list({
            entry["value"]
            for entry in emails_list
            if isinstance(entry, dict) and entry.get("value")
        })

    def get_social_links(self, website: str) -> dict:
        # Hunter.io does not provide social links.
        return {}

    def get_phone_info(self, website: str) -> list[str]:
        # Hunter.io does not provide phone numbers.
        return []
