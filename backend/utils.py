"""
Utility functions replacing Botasaurus bt.* and cl.* helpers.
"""
import platform
from urllib.parse import urlparse


def remove_nones(lst):
    """Remove None values from a list."""
    return [x for x in lst if x is not None]


def get_os():
    """Return the current OS name."""
    return platform.system()


def extract_domain(url):
    """Extract domain from a URL."""
    return urlparse(url).netloc


def extract_path(url):
    """Extract path from a URL."""
    return urlparse(url).path
