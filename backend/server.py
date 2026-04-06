"""
Server configuration and orchestration.

Registers scrapers with botasaurus_server, defines UI views/filters/sorts,
and handles task splitting logic.
"""
import random
import re
import urllib.parse
from urllib.parse import urlparse

from botasaurus import bt, cl
from botasaurus.cache import DontCache
from botasaurus.request import request
from botasaurus.task import task
from botasaurus_server.server import Server
from botasaurus_server.ui import (
    View, Field, ExpandListField, CustomField, filters, sorts,
)

from backend.scrapers.places import scrape_places
from backend.scrapers.reviews import scrape_reviews
from backend.scrapers.social import (
    scrape_social, get_website_contacts,
    make_empty_social,
    FAILED_DUE_TO_CREDITS_EXHAUSTED,
    FAILED_DUE_TO_NOT_SUBSCRIBED,
    FAILED_DUE_TO_UNKNOWN_ERROR,
)
from backend.scrapers.filters import filter_places, sort_dict_by_keys
from backend.data.countries import get_cities
from backend.data.categories import category_options as CATEGORY_OPTIONS


# ---------------------------------------------------------------------------
# Task splitting
# ---------------------------------------------------------------------------

def _clean_query(s):
    if isinstance(s, str):
        return re.sub(r"\s+", " ", s.strip().lower())
    return s


def _is_url(s):
    return s.startswith("http://") or s.startswith("https://")


def _split_gmaps_links(links):
    """Separate Google Maps search URLs from place URLs."""
    search_queries = []
    place_links = []

    for link in links:
        path = cl.extract_path_from_link(link)
        if path.startswith("/maps/search"):
            query = urllib.parse.unquote_plus(
                path.lstrip("/maps/search/").split("/")[0]
            ).strip()
            if query:
                search_queries.append(query)
            elif "query_place_id" in link:
                place_links.append(link)
        else:
            place_links.append(link)

    return place_links, search_queries


def split_task_by_query(data):
    """Split a task into sub-tasks based on queries or country+business_type."""
    if data["country"]:
        cities = get_cities(data["country"])

        if data["randomize_cities"]:
            cities = cities.copy()
            random.shuffle(cities)

        if data["max_cities"]:
            cities = cities[:data["max_cities"]]

        queries = [f"{data['business_type']} in {city}" for city in cities]
        del data["queries"]
        return [
            {**data, "query": _clean_query(q)} for q in queries
        ]

    queries = data["queries"]
    del data["queries"]

    urls = [q for q in queries if _is_url(q)]
    place_links, search_queries = _split_gmaps_links(urls)

    url_set = set(urls)
    for q in queries:
        if q not in url_set:
            search_queries.append(q)

    tasks = [{**data, "query": _clean_query(q)} for q in search_queries]

    if place_links:
        tasks.insert(0, {**data, "links": place_links, "query": "Links"})

    return tasks


def get_task_name(data):
    return data["query"]


# ---------------------------------------------------------------------------
# Social data merging
# ---------------------------------------------------------------------------

def _merge_social_data(places, social_results, should_scrape):
    """Merge social scraper results back into place dicts."""
    success = {}
    errors = {}

    for detail in (social_results or []):
        if detail is None:
            continue
        pid = detail.get("place_id")
        if detail.get("error") is None:
            success[pid] = detail
        else:
            errors[pid] = detail["error"]

    for place in places:
        pid = place.get("place_id")

        if pid in success:
            place.update(success[pid].get("data", {}))
        elif pid in errors:
            err = errors[pid]
            if err == FAILED_DUE_TO_CREDITS_EXHAUSTED:
                msg = "Credit exhaustion. Upgrade at RapidAPI."
            elif err == FAILED_DUE_TO_NOT_SUBSCRIBED:
                msg = "Not subscribed to API. Subscribe at RapidAPI."
            else:
                msg = "Unknown error getting social details."
            place.update(make_empty_social(msg))
        elif place.get("website"):
            if should_scrape:
                place.update(make_empty_social("Failed to get social details."))
            else:
                place.update(make_empty_social("Provide API Key"))
        else:
            place.update(make_empty_social())

    return places


# ---------------------------------------------------------------------------
# Review merging
# ---------------------------------------------------------------------------

def _merge_reviews(places, review_results):
    """Merge scraped reviews back into place dicts."""
    review_map = {}
    for r in (review_results or []):
        review_map[r["place_id"]] = r["reviews"]

    for place in places:
        place["detailed_reviews"] = review_map.get(place["place_id"], [])

    return places


# ---------------------------------------------------------------------------
# Main scraper pipeline
# ---------------------------------------------------------------------------

# Canonical field order for output
SOCIAL_MEDIA_KEYS = [
    "emails", "phones", "linkedin", "twitter", "facebook",
    "youtube", "instagram", "pinterest", "github", "snapchat", "tiktok",
]

DETECTION_KEYS = [
    "technologies", "cms", "ad_pixels", "has_contact_form", "form_provider",
]

OUTPUT_FIELDS = [
    "place_id", "name", "description", "is_spending_on_ads", "reviews",
    "competitors", "website", "can_claim",
] + SOCIAL_MEDIA_KEYS + [
    "owner", "featured_image", "main_category", "categories", "rating",
    "workday_timing", "is_temporarily_closed", "is_permanently_closed",
    "closed_on", "phone", "address", "review_keywords", "link", "status",
    "price_range", "reviews_per_rating", "featured_question", "reviews_link",
    "coordinates", "plus_code", "detailed_address", "time_zone", "cid",
    "data_id", "about", "images", "hours", "most_popular_times",
    "popular_times", "menu", "reservations", "order_online_links",
] + DETECTION_KEYS + [
    "lead_score", "pitch_summary",
    "review_sentiment", "review_themes",
    "featured_reviews", "detailed_reviews", "query",
]


@request()
def google_maps_scraper(_, data):
    """Main pipeline: scrape places, optionally enrich with social + reviews."""
    api_key = data["api_key"]
    lang = data["lang"]
    max_results = data["max_results"]
    do_reviews = data["enable_reviews_extraction"]
    max_reviews = data["max_reviews"]
    reviews_sort = data["reviews_sort"]
    geo_coordinates = data["coordinates"]
    zoom = data["zoom_level"]
    query = data["query"]
    links = data.get("links")

    # 1. Scrape places
    place_data = {
        "query": query,
        "max": max_results,
        "lang": lang,
        "geo_coordinates": geo_coordinates,
        "zoom": zoom,
        "links": links,
    }
    places_obj = scrape_places(place_data)

    if places_obj is None:
        return DontCache([])

    places = places_obj["places"]
    should_scrape_socials = bool(api_key)

    # 2. Enrich with social data
    if should_scrape_socials:
        social_input = [
            {"place_id": p["place_id"], "website": p["website"], "key": api_key}
            for p in places if p.get("website")
        ]
        social_results = bt.remove_nones(scrape_social(social_input))
    else:
        social_results = []

    places = _merge_social_data(places, social_results, should_scrape_socials)

    # 3. Scrape detailed reviews
    if do_reviews:
        reviews_input = [
            {
                "place_id": p["place_id"],
                "link": p["link"],
                "max": min(max_reviews, p["reviews"]) if max_reviews else p["reviews"],
                "reviews_sort": reviews_sort,
                "lang": lang or "en",
            }
            for p in places if p.get("reviews", 0) >= 1
        ]
        review_results = scrape_reviews(reviews_input)
    else:
        review_results = []

    places = _merge_reviews(places, review_results)

    # 4. Order fields and return
    social_keys = SOCIAL_MEDIA_KEYS if api_key else []
    all_fields = [f for f in OUTPUT_FIELDS if f not in SOCIAL_MEDIA_KEYS or f in social_keys]
    return [sort_dict_by_keys(p, all_fields) for p in places]


# ---------------------------------------------------------------------------
# Website contacts scraper (standalone)
# ---------------------------------------------------------------------------

def _get_website_task_name(data):
    domains = []
    for url in data["websites"]:
        netloc = urlparse(url).netloc
        if netloc.startswith("www."):
            netloc = netloc[4:]
        parts = netloc.split(".")
        domains.append(parts[0] if len(parts) <= 2 else ".".join(parts[:-1]))

    if len(domains) == 1:
        return domains[0]
    if len(domains) == 2:
        return f"{domains[0]} and {domains[1]}"
    return f"{domains[0]}, {domains[1]} and {len(domains) - 2} more"


@task()
def website_contacts_scraper(data):
    """Standalone scraper: get social/contact info for a list of websites."""
    websites = data["websites"]
    items = get_website_contacts(websites, metadata=data["api_key"])
    output = []
    has_error = False

    for i, item in enumerate(items):
        if item and item.get("error"):
            output.append({"website": websites[i], **make_empty_social(item["error"])})
            has_error = True
        elif item and item.get("data"):
            output.append({"website": websites[i], **item["data"]})
        else:
            output.append({"website": websites[i], **make_empty_social("Failed")})
            has_error = True

    return DontCache(output) if has_error else output


# ---------------------------------------------------------------------------
# UI configuration
# ---------------------------------------------------------------------------

join_with_commas = lambda value, record: ", ".join(value or []) if isinstance(value, list) else value

def _competitors_to_string(data):
    if not isinstance(data, list):
        return data
    lines = []
    for c in data:
        lines.append(
            f"Name: {c.get('name', 'N/A')}\n"
            f"Link: {c.get('link', 'N/A')}\n"
            f"Reviews: {c.get('reviews', 'N/A')} reviews"
        )
    return "\n\n".join(lines)


def _show_if_api_key(input_data):
    return bool(input_data.get("api_key"))


social_fields = [
    Field("emails", map=join_with_commas, show_if=_show_if_api_key),
    Field("phones", map=join_with_commas, show_if=_show_if_api_key),
    Field("linkedin", show_if=_show_if_api_key),
    Field("twitter", show_if=_show_if_api_key),
    Field("facebook", show_if=_show_if_api_key),
    Field("youtube", show_if=_show_if_api_key),
    Field("instagram", show_if=_show_if_api_key),
]

overview_view = View(
    "Overview",
    fields=[
        Field("place_id"),
        Field("name"),
        Field("reviews"),
        Field("main_category"),
        Field("categories", map=join_with_commas),
        Field("rating"),
        Field("address"),
        Field("link"),
        Field("query"),
        Field("description"),
        Field("is_spending_on_ads"),
        Field("competitors", map=lambda v, r: _competitors_to_string(v)),
        Field("website"),
        Field("can_claim"),
    ] + social_fields + [
        Field("featured_image"),
        Field("workday_timing"),
        Field("is_temporarily_closed"),
        Field("closed_on", map=lambda v, r: ", ".join(v) if isinstance(v, list) else v),
        Field("phone"),
        Field("review_keywords", map=lambda v, r: ", ".join(kw["keyword"] for kw in v) if isinstance(v, list) else v),
    ],
)

featured_reviews_view = View(
    "Featured Reviews",
    fields=[
        Field("place_id"),
        Field("name", output_key="place_name"),
        ExpandListField("featured_reviews", fields=[
            Field("review_id"),
            Field("rating"),
            Field("review_text"),
            Field("published_at"),
            Field("published_at_date"),
            Field("response_from_owner_text"),
            Field("response_from_owner_ago"),
            Field("response_from_owner_date"),
            Field("review_likes_count"),
            Field("total_number_of_reviews_by_reviewer"),
            Field("total_number_of_photos_by_reviewer"),
            Field("is_local_guide"),
            Field("review_translated_text"),
            Field("response_from_owner_translated_text"),
            Field("review_photos"),
        ]),
    ],
)

detailed_reviews_view = View(
    "Detailed Reviews",
    fields=[
        Field("place_id"),
        Field("name", output_key="place_name"),
        ExpandListField("detailed_reviews", fields=[
            Field("review_id"),
            Field("rating"),
            Field("review_text"),
            Field("published_at"),
            Field("published_at_date"),
            Field("response_from_owner_text"),
            Field("response_from_owner_ago"),
            Field("response_from_owner_date"),
            Field("review_likes_count"),
            Field("total_number_of_reviews_by_reviewer"),
            Field("total_number_of_photos_by_reviewer"),
            Field("is_local_guide"),
            Field("review_translated_text"),
            Field("response_from_owner_translated_text"),
        ]),
    ],
)

best_customers_sort = sorts.Sort(
    label="Best Potential Customers",
    is_default=True,
    sorts=[
        sorts.AlphabeticAscendingSort("name"),
        sorts.NumericDescendingSort("reviews"),
        sorts.TrueFirstSort("website"),
        sorts.TruthyFirstSort("linkedin"),
    ],
)

gmaps_filters = [
    filters.MinNumberInput("reviews", label="Min Reviews"),
    filters.MaxNumberInput("reviews", label="Max Reviews"),
    filters.BoolSelectDropdown("website", prioritize_no=True),
    filters.IsTruthyCheckbox("phone"),
    filters.IsTrueCheckbox("is_spending_on_ads"),
    filters.BoolSelectDropdown("can_claim"),
    filters.BoolSelectDropdown("is_temporarily_closed", label="Is Open", invert_filter=True),
    filters.MultiSelectDropdown("categories", label="Category In", options=CATEGORY_OPTIONS),
    filters.MinNumberInput("rating", label="Min Rating"),
]


# ---------------------------------------------------------------------------
# Register scrapers with the server
# ---------------------------------------------------------------------------

Server.add_scraper(
    google_maps_scraper,
    create_all_task=True,
    split_task=split_task_by_query,
    get_task_name=get_task_name,
    filters=gmaps_filters,
    sorts=[
        best_customers_sort,
        sorts.NumericDescendingSort("reviews"),
        sorts.NumericAscendingSort("reviews"),
        sorts.NumericAscendingSort("name"),
    ],
    views=[
        overview_view,
        featured_reviews_view,
        detailed_reviews_view,
    ],
    remove_duplicates_by="place_id",
)

SOCIAL_FILTER_FIELDS = [
    "emails", "phones", "linkedin", "twitter", "facebook",
    "youtube", "instagram", "github", "snapchat", "tiktok",
]

Server.add_scraper(
    website_contacts_scraper,
    get_task_name=_get_website_task_name,
    filters=[
        filters.SearchTextInput("website"),
        *[filters.BoolSelectDropdown(f) for f in SOCIAL_FILTER_FIELDS],
    ],
    sorts=[
        sorts.AlphabeticAscendingSort("website"),
        sorts.AlphabeticDescendingSort("website"),
    ],
)

Server.set_rate_limit(request=1, task=1)
Server.enable_cache()
Server.configure(
    title="Mapo — Google Maps Scraper",
    header_title="Mapo",
    description="Extract business data from Google Maps with enrichment, detection, and AI analysis.",
    right_header={
        "text": "Mapo",
        "link": "#",
    },
)


# ---------------------------------------------------------------------------
# Register REST API routes
# ---------------------------------------------------------------------------
try:
    from backend.api import register_routes
    register_routes()
except Exception as e:
    print(f"[Mapo] Warning: Could not register REST API routes: {e}")
