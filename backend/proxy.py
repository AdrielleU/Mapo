"""
Proxy management for Mapo.

Loads proxy list from config, validates formats, and provides rotation
strategies (round-robin, random, geo-matched).
"""
import random
import threading
from urllib.parse import urlparse

from backend.config import config


# Pool of current Chrome user agents for rotation
UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


def get_random_ua():
    """Return a random user agent from the pool."""
    return random.choice(UA_POOL)


class ProxyManager:
    """Manages proxy rotation for scraping requests."""

    def __init__(self):
        self._proxies = config.proxy.urls if config.proxy.enabled else []
        self._rotation = config.proxy.rotation
        self._index = 0
        self._lock = threading.Lock()

    @property
    def enabled(self):
        return bool(self._proxies)

    def get_proxy(self, country_code=None):
        """
        Get next proxy URL based on rotation strategy.

        Args:
            country_code: Optional ISO country code for geo-matching.

        Returns:
            Proxy URL string, or None if no proxies configured.
        """
        if not self._proxies:
            return None

        if self._rotation == "geo_match" and country_code:
            matched = self._find_geo_proxy(country_code)
            if matched:
                return matched

        if self._rotation == "random":
            return random.choice(self._proxies)

        # Round-robin (default)
        with self._lock:
            proxy = self._proxies[self._index % len(self._proxies)]
            self._index += 1
            return proxy

    def get_proxy_dict(self, country_code=None):
        """Get proxy as a dict suitable for httpx/requests."""
        proxy = self.get_proxy(country_code)
        if not proxy:
            return None
        return {"http://": proxy, "https://": proxy}

    def _find_geo_proxy(self, country_code):
        """Find a proxy whose URL/label contains the country code."""
        code = country_code.lower()
        candidates = [p for p in self._proxies if code in p.lower()]
        if candidates:
            return random.choice(candidates)
        return None

    @staticmethod
    def validate_proxy_url(url):
        """Check if a proxy URL is valid."""
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https", "socks5", "socks5h") and bool(parsed.hostname)


# Singleton
proxy_manager = ProxyManager()
