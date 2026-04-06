"""
Apollo.io enrichment provider.

Uses the Apollo Mixed People Search API to find emails and social
links associated with a given domain/organization.
"""
import logging
from urllib.parse import urlparse

import httpx

from backend.enrichment.base import EnrichmentProvider
from backend.config import config

logger = logging.getLogger(__name__)

APOLLO_API_URL = "https://api.apollo.io/api/v1/mixed_people/search"


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
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


class ApolloProvider(EnrichmentProvider):
    """Enrichment via the Apollo.io People/Organization Search API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or config.enrichment.api_key

    def _build_client(self) -> httpx.Client:
        proxy = _get_proxy()
        return httpx.Client(proxy=proxy, timeout=30)

    def _request(self, website: str) -> dict:
        domain = _extract_domain(website)
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key,
        }
        body = {
            "q_organization_domains": domain,
            "page": 1,
            "per_page": 25,
        }

        with self._build_client() as client:
            try:
                resp = client.post(APOLLO_API_URL, headers=headers, json=body)

                if resp.status_code == 401:
                    logger.error("Apollo authentication error — check API key")
                    return {}
                if resp.status_code == 429:
                    logger.warning("Apollo rate-limited (429)")
                    return {}

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPStatusError as exc:
                logger.error("Apollo HTTP error: %s", exc)
                return {}
            except httpx.RequestError as exc:
                logger.error("Apollo request error: %s", exc)
                return {}

    # -- internal helpers -------------------------------------------------

    @staticmethod
    def _extract_emails(data: dict) -> list[str]:
        emails: set[str] = set()
        for person in data.get("people", []):
            email = person.get("email")
            if email:
                emails.add(email)
        for org in data.get("organizations", []):
            # Some Apollo responses embed an org-level email
            email = org.get("primary_email")
            if email:
                emails.add(email)
        return list(emails)

    @staticmethod
    def _extract_social_links(data: dict) -> dict[str, str]:
        links: dict[str, str] = {}
        # Try organisation-level social links first
        for org in data.get("organizations", []):
            for key in ("linkedin_url", "facebook_url", "twitter_url"):
                value = org.get(key)
                if value and key.replace("_url", "") not in links:
                    links[key.replace("_url", "")] = value
            website = org.get("website_url")
            if website:
                links.setdefault("website", website)
        # Fall back to person-level LinkedIn
        for person in data.get("people", []):
            linkedin = person.get("linkedin_url")
            if linkedin and "linkedin" not in links:
                links["linkedin"] = linkedin
        return links

    @staticmethod
    def _extract_phones(data: dict) -> list[str]:
        phones: set[str] = set()
        for person in data.get("people", []):
            for phone_entry in person.get("phone_numbers", []):
                number = phone_entry.get("sanitized_number") or phone_entry.get("number")
                if number:
                    phones.add(number)
        for org in data.get("organizations", []):
            phone = org.get("phone")
            if phone:
                phones.add(phone)
        return list(phones)

    # -- public interface -------------------------------------------------

    def get_emails(self, website: str) -> list[str]:
        data = self._request(website)
        return self._extract_emails(data)

    def get_social_links(self, website: str) -> dict:
        data = self._request(website)
        return self._extract_social_links(data)

    def get_phone_info(self, website: str) -> list[str]:
        data = self._request(website)
        return self._extract_phones(data)

    def enrich(self, website: str) -> dict:
        """Single API call to get everything at once."""
        data = self._request(website)
        if not data:
            return {"emails": [], "social_links": {}, "phones": []}
        return {
            "emails": self._extract_emails(data),
            "social_links": self._extract_social_links(data),
            "phones": self._extract_phones(data),
        }
