"""
Simple file-based cache for scraping results.

Caches place data by URL hash so re-running the same query
doesn't re-fetch already-scraped pages.
"""
import hashlib
import json
import os
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"


def _hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def get(key):
    """Get cached value by key. Returns None if not cached."""
    path = CACHE_DIR / f"{_hash_key(key)}.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def put(key, value):
    """Cache a value by key."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_hash_key(key)}.json"
    try:
        with open(path, "w") as f:
            json.dump(value, f)
    except OSError:
        pass


def clear():
    """Clear all cached data."""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()


def stats():
    """Return cache stats."""
    if not CACHE_DIR.exists():
        return {"entries": 0, "size_mb": 0}
    files = list(CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in files)
    return {"entries": len(files), "size_mb": round(total_size / 1_048_576, 2)}
