"""Detect advertising / analytics pixels embedded in HTML."""

from __future__ import annotations

import re
from typing import Optional


def _first_match(pattern: str, text: str) -> Optional[str]:
    """Return the first capture group of *pattern* in *text*, or None."""
    m = re.search(pattern, text)
    return m.group(1) if m else None


def detect_ad_pixels(html: str) -> dict:
    """Scan *html* for common ad / analytics pixel snippets.

    Returns a dict with a key per platform.  The value is the extracted
    pixel / measurement ID when one could be parsed, the string
    ``"detected"`` when the pixel is present but no ID was extracted,
    or ``None`` when the pixel was not found.
    """
    if not html:
        return {
            "facebook_pixel": None,
            "google_ads": None,
            "google_analytics": None,
            "linkedin_insight": None,
            "tiktok_pixel": None,
            "twitter_pixel": None,
            "pinterest_tag": None,
        }

    # --- Facebook Pixel ---------------------------------------------------
    facebook_pixel: Optional[str] = None
    if "fbq(" in html or "facebook.com/tr" in html:
        # Try to grab the pixel ID from fbq('init', 'NNNN')
        facebook_pixel = _first_match(r"fbq\s*\(\s*['\"]init['\"]\s*,\s*['\"](\d+)['\"]", html)
        if facebook_pixel is None:
            # Try the img-tag variant: facebook.com/tr?id=NNNN
            facebook_pixel = _first_match(r"facebook\.com/tr\?id=(\d+)", html)
        if facebook_pixel is None:
            facebook_pixel = "detected"

    # --- Google Ads --------------------------------------------------------
    google_ads: Optional[str] = None
    if "gtag(" in html and "AW-" in html:
        google_ads = _first_match(r"(AW-[\w-]+)", html)
        if google_ads is None:
            google_ads = "detected"

    # --- Google Analytics --------------------------------------------------
    google_analytics: Optional[str] = None
    if "gtag(" in html or "google-analytics.com" in html or "googletagmanager.com" in html:
        # GA4 measurement ID
        ga4 = _first_match(r"(G-[A-Z0-9]+)", html)
        # Universal Analytics property ID
        ua = _first_match(r"(UA-\d+-\d+)", html)
        google_analytics = ga4 or ua
        if google_analytics is None and ("gtag(" in html or "google-analytics.com" in html):
            google_analytics = "detected"

    # --- LinkedIn Insight --------------------------------------------------
    linkedin_insight: Optional[str] = None
    if "_linkedin_partner_id" in html or "snap.licdn.com" in html:
        linkedin_insight = _first_match(r"_linkedin_partner_id\s*=\s*['\"]?(\d+)", html)
        if linkedin_insight is None:
            linkedin_insight = "detected"

    # --- TikTok Pixel ------------------------------------------------------
    tiktok_pixel: Optional[str] = None
    if "ttq.load" in html or "analytics.tiktok.com" in html:
        tiktok_pixel = _first_match(r"ttq\.load\s*\(\s*['\"]([A-Z0-9]+)['\"]", html)
        if tiktok_pixel is None:
            tiktok_pixel = "detected"

    # --- Twitter / X Pixel -------------------------------------------------
    twitter_pixel: Optional[str] = None
    if "twq(" in html or "static.ads-twitter.com" in html:
        twitter_pixel = _first_match(r"twq\s*\(\s*['\"]init['\"]\s*,\s*['\"]([a-z0-9]+)['\"]", html)
        if twitter_pixel is None:
            twitter_pixel = "detected"

    # --- Pinterest Tag -----------------------------------------------------
    pinterest_tag: Optional[str] = None
    if "pintrk(" in html or "ct.pinterest.com" in html:
        pinterest_tag = _first_match(r"pintrk\s*\(\s*['\"]load['\"]\s*,\s*['\"](\d+)['\"]", html)
        if pinterest_tag is None:
            pinterest_tag = "detected"

    return {
        "facebook_pixel": facebook_pixel,
        "google_ads": google_ads,
        "google_analytics": google_analytics,
        "linkedin_insight": linkedin_insight,
        "tiktok_pixel": tiktok_pixel,
        "twitter_pixel": twitter_pixel,
        "pinterest_tag": pinterest_tag,
    }
