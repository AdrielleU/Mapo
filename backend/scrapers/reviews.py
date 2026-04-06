"""
Detailed reviews scraper using Google Maps' internal review API.

Paginates through reviews with sort/language options and parses
review HTML/JSON for structured output.
"""
import math
import time
import traceback
import urllib.parse
from datetime import datetime

import regex as re
import httpx
from lxml import html

from .time_utils import parse_relative_date
from botasaurus.request import request
from backend.proxy import proxy_manager, get_random_ua

SORT_OPTIONS = {
    "most_relevant": "qualityScore",
    "newest": "newestFirst",
    "highest_rating": "ratingHigh",
    "lowest_rating": "ratingLow",
}

REQUEST_INTERVAL = 0.2
MAX_RETRIES = 10
RETRY_WAIT = 30


class GoogleMapsAPIScraper:
    """Scrapes reviews from Google Maps' internal API endpoints."""

    def __init__(self):
        proxy_dict = proxy_manager.get_proxy_dict()
        self._session = httpx.Client(
            http2=True,
            timeout=30.0,
            proxy=proxy_dict.get("https://") if proxy_dict else None,
        )
        self._headers = {
            "User-Agent": get_random_ua(),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._session.close()

    def _make_request(self, url, retries=MAX_RETRIES):
        """Make a request with retry logic."""
        for attempt in range(retries):
            try:
                resp = self._session.get(url, headers=self._headers)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code == 429:
                    time.sleep(RETRY_WAIT)
                    continue
            except Exception:
                traceback.print_exc()
                if attempt < retries - 1:
                    time.sleep(RETRY_WAIT)
        return None

    def _extract_feature_id(self, place_url):
        """Extract the feature ID (data parameter) from a Google Maps place URL."""
        parsed = urllib.parse.urlparse(place_url)
        path = parsed.path
        # Try to get from data parameter
        if "data=" in place_url:
            data_part = place_url.split("data=")[1].split("&")[0].split("?")[0]
            parts = data_part.split("!")
            for i, part in enumerate(parts):
                if part.startswith("1s"):
                    return part[2:]
        return None

    def _build_reviews_url(self, feature_id, token, sort_by, lang):
        """Build the internal Google Maps reviews API URL."""
        sort_value = SORT_OPTIONS.get(sort_by, "newestFirst")
        base = "https://www.google.com/maps/rpc/listugcposts"

        # Build the protobuf-like parameter
        params = {
            "authuser": "0",
            "hl": lang,
            "gl": lang[:2] if len(lang) >= 2 else "us",
            "pb": (
                f"!1m7!1s{feature_id}!3s!6m4!4m1!1e1!4m1!1e3"
                f"!2m2!1i10!2s{token or ''}"
                f"!3e{SORT_OPTIONS.get(sort_by, 'newestFirst')}"
                f"!5m2!1s{lang}!2s{lang[:2] if len(lang) >= 2 else 'us'}"
            ),
        }
        return f"{base}?{urllib.parse.urlencode(params)}"

    def scrape_reviews(self, place_url, max_reviews, lang="en", sort_by="newest"):
        """
        Scrape reviews for a place.

        Args:
            place_url: Google Maps place URL
            max_reviews: Maximum number of reviews to fetch
            lang: Language code
            sort_by: Sort option (newest, most_relevant, highest_rating, lowest_rating)

        Returns:
            List of review dicts
        """
        retrieval_date = str(datetime.now())
        reviews = []
        token = ""

        while len(reviews) < max_reviews:
            feature_id = self._extract_feature_id(place_url)
            if not feature_id:
                break

            url = self._build_reviews_url(feature_id, token, sort_by, lang)
            response_text = self._make_request(url)

            if not response_text:
                break

            try:
                batch = self._parse_reviews_response(response_text, retrieval_date, lang)
                new_reviews = batch.get("reviews", [])
                token = batch.get("token", "")

                if not new_reviews:
                    break

                reviews.extend(new_reviews)

                if not token:
                    break

                time.sleep(REQUEST_INTERVAL)
            except Exception:
                traceback.print_exc()
                break

        return reviews[:max_reviews]

    def _parse_reviews_response(self, text, retrieval_date, lang):
        """Parse the raw API response into structured review data."""
        # The response starts with )]}'
        if text.startswith(")]}'"):
            text = text[4:]

        try:
            import json
            data = json.loads(text)
        except Exception:
            return {"reviews": [], "token": ""}

        reviews = []
        raw_reviews = data[2] if len(data) > 2 and data[2] else []

        for entry in raw_reviews:
            try:
                review = self._parse_single_review(entry, retrieval_date, lang)
                if review:
                    reviews.append(review)
            except Exception:
                continue

        token = data[1] if len(data) > 1 else ""

        return {"reviews": reviews, "token": token or ""}

    def _parse_single_review(self, entry, retrieval_date, lang):
        """Parse a single review entry from the API response."""
        if not entry or not isinstance(entry, list):
            return None

        review_data = entry[0] if entry else None
        if not review_data:
            return None

        # Extract fields from the nested structure
        relative_date = _safe_get(review_data, 1, 6)
        rating = _safe_get(review_data, 2, 0, 0)
        text = _safe_get(review_data, 2, 15, 0, 0)
        review_id = review_data[0] if review_data else None
        translated_text = _safe_get(review_data, 2, 15, 1, 0)

        response_text = _safe_get(review_data, 3, 14, 0, 0)
        response_relative_date = _safe_get(review_data, 3, 3)
        translated_response = _safe_get(review_data, 3, 14, 1, 0)

        likes = _safe_get(review_data, 4, 1) or -1
        user_reviews = _safe_get(review_data, 1, 4, 0, 1)
        user_photos = _safe_get(review_data, 1, 4, 0, 2)

        is_local_guide = _safe_get(review_data, 1, 4, 0, 12, 0)
        if is_local_guide and isinstance(is_local_guide, str):
            is_local_guide = "local " in is_local_guide.lower()
        else:
            is_local_guide = False

        text_date = None
        if relative_date:
            try:
                text_date = parse_relative_date(relative_date, retrieval_date, hl=lang)
            except Exception:
                pass

        response_text_date = None
        if response_relative_date:
            try:
                response_text_date = parse_relative_date(
                    response_relative_date, retrieval_date, hl=lang
                )
            except Exception:
                pass

        return {
            "review_id": review_id,
            "rating": int(rating) if rating else 0,
            "text": text or "",
            "relative_date": relative_date or "",
            "text_date": text_date,
            "translated_text": translated_text or "",
            "response_text": response_text or "",
            "response_relative_date": response_relative_date or "",
            "response_text_date": response_text_date,
            "translated_response_text": translated_response or "",
            "likes": likes,
            "user_reviews": user_reviews,
            "user_photos": user_photos,
            "user_is_local_guide": is_local_guide,
            "retrieval_date": retrieval_date,
        }


def _safe_get(data, *keys):
    for key in keys:
        try:
            data = data[key]
        except (IndexError, TypeError, KeyError):
            return None
    return data


def _process_reviews(reviews):
    """Transform raw review dicts into the output format."""
    processed = []
    for review in reviews:
        lk = review.get("likes", -1)
        processed.append({
            "review_id": review.get("review_id"),
            "rating": int(review.get("rating", 0)),
            "review_text": review.get("text"),
            "published_at": review.get("relative_date"),
            "published_at_date": review.get("text_date"),
            "response_from_owner_text": review.get("response_text") or None,
            "response_from_owner_ago": review.get("response_relative_date") or None,
            "response_from_owner_date": review.get("response_text_date"),
            "review_likes_count": 0 if lk <= -1 else lk,
            "total_number_of_reviews_by_reviewer": review.get("user_reviews"),
            "total_number_of_photos_by_reviewer": review.get("user_photos"),
            "is_local_guide": review.get("user_is_local_guide"),
            "review_translated_text": review.get("translated_text"),
            "response_from_owner_translated_text": review.get("translated_response_text"),
        })
    return processed


@request(
    close_on_crash=True,
    output=None,
    parallel=40,
)
def scrape_reviews(requests, data):
    """
    Botasaurus task: scrape detailed reviews for a single place.

    Args:
        data: dict with place_id, link, max, reviews_sort, lang
    """
    place_id = data["place_id"]
    link = data["link"]
    max_r = data["max"]
    sort_by = data["reviews_sort"]
    lang = data["lang"]

    with GoogleMapsAPIScraper() as scraper:
        raw_reviews = scraper.scrape_reviews(link, max_r, lang, sort_by=sort_by)
        processed = _process_reviews(raw_reviews)

    return {"place_id": place_id, "reviews": processed}
