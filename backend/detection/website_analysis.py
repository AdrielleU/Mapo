"""
Deep website analysis — goes beyond tech detection to assess
the quality and maturity of a business's online presence.

This helps score leads: a business with a bad/old website is a
better prospect for web services than one with a modern site.
"""
from __future__ import annotations

import re
from typing import Optional


def analyze_website(html: str, url: str = "") -> dict:
    """
    Analyze a website's HTML for quality signals, online presence maturity,
    and business intelligence indicators.

    Returns a dict with all analysis results.
    """
    if not html:
        return _empty_result()

    html_lower = html.lower()

    return {
        # Website quality signals
        "has_ssl": url.startswith("https://") if url else None,
        "is_mobile_responsive": _check_mobile_responsive(html_lower),
        "has_meta_description": _check_meta_description(html),
        "has_og_tags": _check_og_tags(html_lower),
        "has_schema_markup": _check_schema_markup(html_lower),
        "page_title": _extract_title(html),

        # Conversion signals
        "has_call_to_action": _check_cta(html_lower),
        "has_phone_clickable": _check_click_to_call(html_lower),
        "has_online_booking": _check_online_booking(html_lower),
        "has_pricing_page": _check_pricing(html_lower),
        "has_testimonials": _check_testimonials(html_lower),
        "has_blog": _check_blog(html_lower),
        "has_faq": _check_faq(html_lower),

        # E-commerce / monetization
        "accepts_online_payments": _check_online_payments(html_lower),
        "has_ecommerce": _check_ecommerce(html_lower),

        # Communication channels
        "has_live_chat": _check_live_chat(html_lower),
        "has_whatsapp": _check_whatsapp(html_lower),
        "has_email_visible": _check_email_visible(html),
        "has_map_embed": _check_map_embed(html_lower),

        # SEO signals
        "has_sitemap_link": _check_sitemap(html_lower),
        "has_robots_meta": _check_robots(html_lower),
        "has_canonical_tag": _check_canonical(html_lower),
        "has_hreflang": _check_hreflang(html_lower),

        # Accessibility
        "has_alt_tags": _check_alt_tags(html),
        "has_aria_labels": _check_aria(html_lower),

        # Quality score (0-100)
        "website_quality_score": None,  # computed below
    }


def score_website(analysis: dict) -> int:
    """Compute a 0-100 website quality score from analysis results."""
    score = 0
    weights = {
        "has_ssl": 10,
        "is_mobile_responsive": 15,
        "has_meta_description": 5,
        "has_og_tags": 3,
        "has_schema_markup": 5,
        "has_call_to_action": 8,
        "has_phone_clickable": 5,
        "has_online_booking": 8,
        "has_testimonials": 5,
        "has_blog": 5,
        "has_live_chat": 5,
        "has_email_visible": 3,
        "has_sitemap_link": 3,
        "has_canonical_tag": 3,
        "has_alt_tags": 5,
        "has_aria_labels": 3,
        "accepts_online_payments": 5,
        "has_faq": 4,
    }
    for key, weight in weights.items():
        if analysis.get(key):
            score += weight
    return min(100, score)


def _empty_result():
    return {k: None for k in [
        "has_ssl", "is_mobile_responsive", "has_meta_description", "has_og_tags",
        "has_schema_markup", "page_title", "has_call_to_action", "has_phone_clickable",
        "has_online_booking", "has_pricing_page", "has_testimonials", "has_blog",
        "has_faq", "accepts_online_payments", "has_ecommerce", "has_live_chat",
        "has_whatsapp", "has_email_visible", "has_map_embed", "has_sitemap_link",
        "has_robots_meta", "has_canonical_tag", "has_hreflang", "has_alt_tags",
        "has_aria_labels", "website_quality_score",
    ]}


# --- Checkers ---

def _check_mobile_responsive(html):
    return "viewport" in html and "width=device-width" in html

def _check_meta_description(html):
    return bool(re.search(r'<meta[^>]+name=["\']description["\']', html, re.I))

def _check_og_tags(html):
    return "og:title" in html or "og:description" in html

def _check_schema_markup(html):
    return "application/ld+json" in html or "itemtype" in html

def _extract_title(html):
    match = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
    return match.group(1).strip()[:200] if match else None

def _check_cta(html):
    cta_patterns = [
        r'book\s*(now|online|appointment|today)',
        r'schedule\s*(now|online|appointment|today|a\s+)',
        r'get\s*(started|a\s+quote|in\s+touch)',
        r'contact\s+us',
        r'request\s*(a\s+)?(quote|consultation|demo|appointment)',
        r'free\s*(consultation|estimate|quote|trial)',
        r'call\s*(us|now|today)',
        r'sign\s*up',
        r'learn\s+more',
    ]
    for pattern in cta_patterns:
        if re.search(pattern, html, re.I):
            return True
    return False

def _check_click_to_call(html):
    return "tel:" in html

def _check_online_booking(html):
    booking_sigs = [
        "book online", "book now", "book appointment", "schedule online",
        "schedule appointment", "online booking", "reserve now",
        "make an appointment", "request appointment",
        "calendly.com", "acuityscheduling", "booksy.com", "vagaro.com",
        "mindbodyonline.com", "zocdoc", "opentable.com", "resy.com",
        "setmore.com", "simplybook.me", "fresha.com",
    ]
    return any(sig in html for sig in booking_sigs)

def _check_pricing(html):
    return any(s in html for s in ["pricing", "our prices", "price list", "rate card", "cost of"])

def _check_testimonials(html):
    return any(s in html for s in ["testimonial", "what our customers say", "client reviews", "patient reviews", "what people say"])

def _check_blog(html):
    return any(s in html for s in ["/blog", "/news", "/articles", "/resources", "blog-post"])

def _check_faq(html):
    return any(s in html for s in ["/faq", "frequently asked", "common questions", "accordion"])

def _check_online_payments(html):
    return any(s in html for s in ["stripe.com", "paypal.com", "square.com", "braintree", "pay online", "pay now", "checkout"])

def _check_ecommerce(html):
    return any(s in html for s in ["add to cart", "add-to-cart", "shopping cart", "woocommerce", "shopify", "bigcommerce", "product-price"])

def _check_live_chat(html):
    return any(s in html for s in [
        "intercom.io", "drift.com", "zendesk.com", "tawk.to", "tidio.co",
        "crisp.chat", "livechatinc", "hubspot.com/conversations", "olark.com",
        "smartsupp", "freshchat", "chatwoot",
    ])

def _check_whatsapp(html):
    return any(s in html for s in ["whatsapp.com", "wa.me/", "api.whatsapp"])

def _check_email_visible(html):
    return bool(re.search(r'mailto:', html)) or bool(re.search(r'[\w.-]+@[\w.-]+\.\w{2,}', html))

def _check_map_embed(html):
    return any(s in html for s in ["google.com/maps/embed", "maps.googleapis.com", "mapbox.com"])

def _check_sitemap(html):
    return "sitemap" in html

def _check_robots(html):
    return bool(re.search(r'<meta[^>]+name=["\']robots["\']', html, re.I))

def _check_canonical(html):
    return bool(re.search(r'<link[^>]+rel=["\']canonical["\']', html, re.I))

def _check_hreflang(html):
    return "hreflang" in html

def _check_alt_tags(html):
    imgs = re.findall(r'<img[^>]+>', html, re.I)
    if not imgs:
        return True  # no images = no problem
    with_alt = sum(1 for img in imgs if 'alt=' in img.lower())
    return with_alt / len(imgs) > 0.5  # more than half have alt tags

def _check_aria(html):
    return "aria-label" in html or "aria-describedby" in html
