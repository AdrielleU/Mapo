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
    """Parse place data from either the preview endpoint or APP_INITIALIZATION_STATE.

    Handles multiple formats as Google's structure evolves:
    1. Preview endpoint: flat array where [6] has 100+ element place data
    2. Old APP_INITIALIZATION_STATE: nested at [3][6] as an escaped JSON string
    3. New APP_INITIALIZATION_STATE: nested at [3][5] as an escaped JSON string
    """
    parsed = json.loads(data)

    # Format 1: preview endpoint — [6] is directly the place data array
    if isinstance(parsed, list) and len(parsed) > 6 and isinstance(parsed[6], list) and len(parsed[6]) > 50:
        return parsed

    # Format 2/3: APP_INITIALIZATION_STATE — data is an escaped string inside [3]
    if isinstance(parsed, list) and len(parsed) > 3 and isinstance(parsed[3], list):
        # Try each index in [3] for an escaped JSON string containing place data
        for idx in (6, 5, -1):
            raw = safe_get(parsed, 3, idx)
            if not isinstance(raw, str):
                continue
            prefix = ")]}'"
            if raw.startswith(prefix):
                raw = raw[len(prefix) + 1:]  # skip prefix + newline
            try:
                inner = json.loads(raw)
                # Check if this inner JSON has a [6] with 50+ elements (place data)
                if isinstance(inner, list) and len(inner) > 6 and isinstance(safe_get(inner, 6), list) and len(inner[6]) > 50:
                    return inner
            except (json.JSONDecodeError, TypeError):
                continue

    # Fallback: search all nested arrays for one with 100+ elements (the place data)
    def _find_place_data(obj, depth=0):
        if depth > 4 or not isinstance(obj, list):
            return None
        if len(obj) > 80 and isinstance(safe_get(obj, 11), (str, type(None))):
            # Looks like place data — verify with a few known indices
            if safe_get(obj, 78) is not None or safe_get(obj, 9) is not None:
                return {"6": obj}  # Wrap so extract_data can access it at [6]
        for item in obj:
            result = _find_place_data(item, depth + 1)
            if result:
                return result
        return None

    found = _find_place_data(parsed)
    if found:
        # Return a structure where [6] is the place data
        result = [None] * 7
        result[6] = found["6"]
        return result

    raise IndexError("Could not find place data in any known format")


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

    # Photos
    featured_image = to_high_res_image(safe_get(data, 6, 37, 0, 0, 6, 0))
    raw_images = safe_get(data, 6, 171, 0) or []
    images = [to_high_res_image(safe_get(img, 6, 0)) for img in raw_images if safe_get(img, 6, 0)]
    image_count = safe_get(data, 6, 171, 3) or len(images)

    # Coordinates
    lat = safe_get(data, 6, 9, 2)
    lng = safe_get(data, 6, 9, 3)
    coordinates = f"{lat},{lng}" if lat and lng else None

    # Owner info
    owner_name = safe_get(data, 6, 57, 1)
    owner_link = safe_get(data, 6, 57, 2)

    # Business hours
    hours_raw = safe_get(data, 6, 34, 1) or []
    hours = {}
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for i, day_data in enumerate(hours_raw):
        if i < len(day_names) and day_data:
            times = safe_get(day_data, 0)
            if times:
                hours[day_names[i]] = times
    closed_on = [day_names[i] for i, d in enumerate(hours_raw) if i < len(day_names) and not d]

    # Is open now / temporarily closed / permanently closed
    is_temporarily_closed = bool(safe_get(data, 6, 72, 0))
    is_permanently_closed = bool(safe_get(data, 6, 88, 0))
    status = "permanently_closed" if is_permanently_closed else "temporarily_closed" if is_temporarily_closed else "operational"

    # Price range ($, $$, $$$, $$$$)
    price_range = safe_get(data, 6, 4, 2)

    # Reviews breakdown by rating
    reviews_per_rating = {}
    for i in range(1, 6):
        count = safe_get(data, 6, 175, 3, i - 1)
        if count is not None:
            reviews_per_rating[str(i)] = count

    # Review keywords (topics people mention)
    raw_keywords = safe_get(data, 6, 175, 10) or []
    review_keywords = []
    for kw in raw_keywords:
        keyword_text = safe_get(kw, 1)
        keyword_count = safe_get(kw, 3)
        if keyword_text:
            review_keywords.append({"keyword": keyword_text, "count": keyword_count})

    # Owner response rate — count featured reviews that have owner responses
    featured_reviews = _extract_featured_reviews(data)
    reviews_with_response = sum(1 for r in featured_reviews if r.get("response_from_owner_text"))
    owner_response_rate = round(reviews_with_response / len(featured_reviews), 2) if featured_reviews else 0

    # Popular times / busy hours
    popular_times = safe_get(data, 6, 84) or []
    most_popular_times = safe_get(data, 6, 84, 0) or []

    # Plus code
    plus_code = safe_get(data, 6, 183, 2, 0)

    # Time zone
    time_zone = safe_get(data, 6, 30)

    # CID (customer ID) and data_id
    cid = safe_get(data, 6, 25)
    data_id = safe_get(data, 6, 10)

    # Claiming status
    can_claim = bool(safe_get(data, 6, 4, 15))

    # About/attributes
    about_raw = safe_get(data, 6, 100) or []
    about = {}
    for section in about_raw:
        section_name = safe_get(section, 0)
        items = safe_get(section, 2) or []
        if section_name and isinstance(section_name, str):
            about[section_name] = [safe_get(item, 1) for item in items if safe_get(item, 1)]

    # Service options (dine-in, takeout, delivery, etc.)
    service_options = []
    for section_name, items in about.items():
        if "service" in section_name.lower():
            service_options.extend(items)

    # Menu link
    menu = clean_link(safe_get(data, 6, 38, 0))

    # Reservation link
    reservations = clean_link(safe_get(data, 6, 46, 0))

    # Order online links
    raw_order_links = safe_get(data, 6, 75) or []
    order_online_links = [clean_link(safe_get(ol, 0)) for ol in raw_order_links if safe_get(ol, 0)]

    # Competitors
    raw_competitors = safe_get(data, 6, 99) or []
    competitors = []
    for comp in raw_competitors:
        comp_name = safe_get(comp, 1)
        comp_link = safe_get(comp, 4)
        comp_reviews = safe_get(comp, 3, 1)
        if comp_name:
            competitors.append({"name": comp_name, "link": comp_link, "reviews": comp_reviews})

    # Featured question
    fq_text = safe_get(data, 6, 185, 0, 0)
    fq_answer = safe_get(data, 6, 185, 0, 1, 0, 0)
    featured_question = {"question": fq_text, "answer": fq_answer} if fq_text else None

    # Phone (international format)
    phone_local = safe_get(data, 6, 178, 0, 0)
    phone_international = safe_get(data, 6, 178, 0, 3)

    return {
        "place_id": place_id,
        "name": safe_get(data, 6, 11),
        "description": safe_get(data, 6, 32, 0, 1) or safe_get(data, 6, 32, 1, 1),
        "reviews": safe_get(data, 6, 4, 8) or 0,
        "rating": safe_get(data, 6, 4, 7) or 0,
        "website": clean_link(safe_get(data, 6, 7, 0)),
        "phone": phone_local,
        "phone_international": phone_international,
        "main_category": safe_get(data, 6, 13, 0),
        "categories": safe_get(data, 6, 13),
        "address": safe_get(data, 6, 39) or safe_get(data, 6, 37, 0, 0, 17, 0),
        "detailed_address": complete_address,
        "coordinates": coordinates,
        "plus_code": plus_code,
        "time_zone": time_zone,
        "cid": cid,
        "data_id": data_id,
        "link": link,
        "reviews_link": reviews_link,
        # Ownership & status
        "owner": owner_name,
        "owner_link": owner_link,
        "can_claim": can_claim,
        "status": status,
        "is_temporarily_closed": is_temporarily_closed,
        "is_permanently_closed": is_permanently_closed,
        # Business details
        "price_range": price_range,
        "hours": hours,
        "closed_on": closed_on,
        "service_options": service_options,
        "about": about,
        "menu": menu,
        "reservations": reservations,
        "order_online_links": order_online_links,
        # Reviews intelligence
        "reviews_per_rating": reviews_per_rating,
        "review_keywords": review_keywords,
        "owner_response_rate": owner_response_rate,
        "featured_question": featured_question,
        # Competition
        "competitors": competitors,
        # Media
        "featured_image": featured_image,
        "images": images,
        "image_count": image_count,
        # Timing / traffic
        "popular_times": popular_times,
        "most_popular_times": most_popular_times,
        # Reviews
        "featured_reviews": featured_reviews,
    }


def extract_possible_map_link(input_str):
    """
    When a Google Maps search returns a single place instead of a list,
    extract that place's link.
    """
    data = parse_possible_map_link(input_str)
    return safe_get(data, 6, 27) or safe_get(data, 0, 1, 0, 14, 27)
