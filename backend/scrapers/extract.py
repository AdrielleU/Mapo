"""
Google Maps data extraction from APP_INITIALIZATION_STATE JSON blobs.

Parses the deeply nested JSON structure that Google Maps embeds in page HTML
and extracts structured business data.
"""
import json
import re
from datetime import datetime

from backend.utils import extract_domain, extract_path


def safe_get(data, *keys):
    """Safely traverse nested lists/dicts by index path."""
    for key in keys:
        try:
            data = data[key]
        except (IndexError, TypeError, KeyError):
            return None
    return data


def parse_app_state(data):
    """Parse the APP_INITIALIZATION_STATE JSON string."""
    raw = json.loads(data)[3][6]
    prefix = ")]}'"
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    return json.loads(raw)


def parse_possible_map_link(data):
    """Parse APP_INITIALIZATION_STATE to extract a single place link."""
    loaded = json.loads(data)
    raw = safe_get(loaded, 3, -1)
    prefix = ")]}'"
    if raw and raw.startswith(prefix):
        raw = raw[len(prefix):]
    return json.loads(raw)


def clean_link(link):
    """Remove tracking params from Google URLs."""
    if link is None:
        return None
    opi_index = link.find("&opi")
    if opi_index != -1:
        link = link[:opi_index]
    if link.startswith("/url?q="):
        link = link[len("/url?q="):]
    return link


def to_high_res_image(img):
    """Convert Google user-content image URLs to 1024px resolution."""
    if not img:
        return img
    domain = extract_domain(img)
    if "googleusercontent." in domain:
        img_id = extract_path(img).split("/")[-1].split("=")[0]
        return f"https://lh3.ggpht.com/p/{img_id}=s1024"
    return img


def _get_hl_from_link(link):
    match = re.search(r"[?&]hl=([^&]+)", link)
    return match.group(1) if match else "en"


def _extract_business_name(url):
    match = re.search(r"maps/place/([^/]+)", url)
    return match.group(1) if match else None


def _generate_reviews_url(place_id, query, authuser, hl, gl):
    base_url = "https://search.google.com/local/reviews"
    params = {"placeid": place_id, "q": query, "authuser": authuser, "hl": hl, "gl": gl}
    query_string = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{base_url}?{query_string}"


def _timestamp_to_iso(timestamp_ms):
    """Convert a millisecond-precision timestamp to ISO date string."""
    seconds = int(timestamp_ms / 1000)
    return datetime.utcfromtimestamp(seconds).isoformat()


def _extract_review_images(data):
    images = []
    for x in (data or []):
        img = safe_get(x, 1, 6, 0)
        images.append(to_high_res_image(img))
    return images


def _extract_featured_reviews(data):
    """Extract embedded/featured reviews from the place page."""
    raw_reviews = safe_get(data, 6, 175, 9, 0, 0) or []
    reviews = []

    for entry in raw_reviews:
        el = entry[0]
        when = safe_get(el, 1, 6)
        rating = safe_get(el, 2, 0, 0)
        text = safe_get(el, 2, 15, 0, 0)
        images = _extract_review_images(safe_get(el, 2, 2) or [])
        review_id = el[0]

        review_translated = safe_get(el, 2, 15, 1, 0)
        owner_response = safe_get(el, 3, 14, 0, 0) or None
        owner_response_translated = safe_get(el, 3, 14, 1, 0) or None

        published_ts = safe_get(el, 1, 2) or safe_get(el, 1, 3)
        published_date = _timestamp_to_iso(published_ts / 1000) if published_ts else None

        owner_response_ago = safe_get(el, 3, 3) or safe_get(el, 3, 4) or None
        owner_response_ts = safe_get(el, 3, 1) or safe_get(el, 3, 2)
        owner_response_date = _timestamp_to_iso(owner_response_ts / 1000) if owner_response_ts else None

        num_reviews = safe_get(el, 1, 4, 0, 1)
        num_photos = safe_get(el, 1, 4, 0, 2)
        likes = safe_get(el, 4, 1)

        is_local_guide = safe_get(el, 1, 4, 0, 12, 0)
        is_local_guide = "local " in is_local_guide.lower() if is_local_guide else False

        reviews.append({
            "review_id": review_id,
            "rating": rating,
            "review_text": text,
            "published_at": when,
            "published_at_date": published_date,
            "response_from_owner_text": owner_response,
            "response_from_owner_ago": owner_response_ago,
            "response_from_owner_date": owner_response_date,
            "review_likes_count": likes,
            "total_number_of_reviews_by_reviewer": num_reviews,
            "total_number_of_photos_by_reviewer": num_photos,
            "is_local_guide": is_local_guide,
            "review_translated_text": review_translated,
            "response_from_owner_translated_text": owner_response_translated,
            "review_photos": images,
        })

    return reviews


def extract_data(input_str, link):
    """
    Main extraction function. Parses the APP_INITIALIZATION_STATE blob
    and returns a structured dict of place data.
    """
    data = parse_app_state(input_str)

    place_id = safe_get(data, 6, 78)
    complete_address = {
        "ward": safe_get(data, 6, 183, 1, 0),
        "street": safe_get(data, 6, 183, 1, 1),
        "city": safe_get(data, 6, 183, 1, 3),
        "postal_code": safe_get(data, 6, 183, 1, 4),
        "state": safe_get(data, 6, 183, 1, 5),
        "country_code": safe_get(data, 6, 183, 1, 6),
    }

    reviews_link = clean_link(safe_get(data, 6, 4, 3, 0))
    if reviews_link is None:
        gl = complete_address["country_code"]
        hl = _get_hl_from_link(link)
        query = _extract_business_name(link)
        reviews_link = _generate_reviews_url(place_id, query, 0, hl, gl)

    # Extract photos
    featured_image = to_high_res_image(safe_get(data, 6, 37, 0, 0, 6, 0))
    raw_images = safe_get(data, 6, 171, 0) or []
    images = [to_high_res_image(safe_get(img, 6, 0)) for img in raw_images if safe_get(img, 6, 0)]
    image_count = safe_get(data, 6, 171, 3) or len(images)

    return {
        "place_id": place_id,
        "name": safe_get(data, 6, 11),
        "description": safe_get(data, 6, 32, 0, 1) or safe_get(data, 6, 32, 1, 1),
        "reviews": safe_get(data, 6, 4, 8) or 0,
        "rating": safe_get(data, 6, 4, 7) or 0,
        "website": clean_link(safe_get(data, 6, 7, 0)),
        "phone": safe_get(data, 6, 178, 0, 0),
        "main_category": safe_get(data, 6, 13, 0),
        "categories": safe_get(data, 6, 13),
        "address": safe_get(data, 6, 39) or safe_get(data, 6, 37, 0, 0, 17, 0),
        "detailed_address": complete_address,
        "link": link,
        "reviews_link": reviews_link,
        "featured_image": featured_image,
        "images": images,
        "image_count": image_count,
        "featured_reviews": _extract_featured_reviews(data),
    }


def extract_possible_map_link(input_str):
    """
    When a Google Maps search returns a single place instead of a list,
    extract that place's link.
    """
    data = parse_possible_map_link(input_str)
    return safe_get(data, 6, 27) or safe_get(data, 0, 1, 0, 14, 27)
