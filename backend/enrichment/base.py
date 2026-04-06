"""
Abstract base class for enrichment providers.

All enrichment providers (RapidAPI, Hunter.io, Apollo, etc.) must
implement this interface so they can be swapped via config.
"""
from abc import ABC, abstractmethod


class EnrichmentProvider(ABC):
    """Standard interface every enrichment provider must satisfy."""

    @abstractmethod
    def get_emails(self, website: str) -> list[str]:
        """Return a list of email addresses found for *website*."""
        ...

    @abstractmethod
    def get_social_links(self, website: str) -> dict:
        """Return a dict of social-network links, e.g. {"facebook": "...", "twitter": "..."}."""
        ...

    @abstractmethod
    def get_phone_info(self, website: str) -> list[str]:
        """Return a list of phone numbers found for *website*."""
        ...

    def enrich(self, website: str) -> dict:
        """Convenience method — calls all three extractors and merges the results."""
        return {
            "emails": self.get_emails(website),
            "social_links": self.get_social_links(website),
            "phones": self.get_phone_info(website),
        }
