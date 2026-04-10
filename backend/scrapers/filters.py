"""
Result filtering and field ordering utilities.
"""


def filter_places(places, criteria):
    """
    Filter a list of places by criteria.

    Supported criteria:
        has_website: bool - filter by website presence
        min_reviews: int - minimum review count
        min_rating: float - minimum star rating
        max_rating: float - maximum star rating
        has_phone: bool - filter by phone presence
        skip_closed: bool - exclude temporarily/permanently closed places
        category_in: list[str] - place must match at least one category
        price_range: str or list[str] - filter by price level ($, $$, etc.)
    """
    def matches(place):
        # has_website
        has_website = criteria.get("has_website")
        if has_website is not None:
            website = place.get("website")
            if has_website and not website:
                return False
            if not has_website and website:
                return False

        # min_reviews
        min_reviews = criteria.get("min_reviews")
        if min_reviews is not None:
            reviews = place.get("reviews")
            if reviews is None or reviews == "" or reviews < min_reviews:
                return False

        # min_rating
        min_rating = criteria.get("min_rating")
        if min_rating is not None:
            rating = place.get("rating")
            if rating is None or rating < min_rating:
                return False

        # max_rating
        max_rating = criteria.get("max_rating")
        if max_rating is not None:
            rating = place.get("rating")
            if rating is not None and rating > max_rating:
                return False

        # has_phone
        has_phone = criteria.get("has_phone")
        if has_phone is not None:
            phone = place.get("phone")
            if has_phone and not phone:
                return False
            if not has_phone and phone:
                return False

        # skip_closed
        if criteria.get("skip_closed"):
            if place.get("is_temporarily_closed") or place.get("is_permanently_closed"):
                return False

        # category_in
        category_in = criteria.get("category_in")
        if category_in:
            place_cats = place.get("categories") or []
            if isinstance(place_cats, str):
                place_cats = [place_cats]
            lower_cats = [c.lower() for c in place_cats]
            if not any(c.lower() in lower_cats for c in category_in):
                return False

        # price_range
        price_range = criteria.get("price_range")
        if price_range is not None:
            place_price = place.get("price_range")
            if isinstance(price_range, list):
                if place_price not in price_range:
                    return False
            elif place_price != price_range:
                return False

        return True

    return [p for p in places if matches(p)]


def sort_dict_by_keys(dictionary, keys):
    """Reorder dict keys to match a canonical field order."""
    return {key: dictionary[key] for key in keys if key in dictionary}


def load_existing_keys(source: str, field: str = "place_id", is_data: bool = False) -> set[str]:
    """Load a CSV/JSON file or base64 string and return a set of values for the given field.

    Args:
        source: file path OR base64-encoded CSV data (when is_data=True)
        field: column/key to extract (e.g. "place_id", "name", "phone")
        is_data: True if source is base64 CSV data, False if it's a file path

    Returns:
        Set of stripped string values from the field column.
    """
    import csv
    import json as _json
    import base64
    import io

    def _from_csv_text(text: str) -> set[str]:
        reader = csv.DictReader(io.StringIO(text))
        return {row.get(field, "").strip() for row in reader if row.get(field)}

    if is_data:
        text = base64.b64decode(source).decode("utf-8")
        return _from_csv_text(text)

    # File path
    if source.endswith(".json"):
        with open(source) as f:
            items = _json.load(f)
        return {str(item.get(field, "")).strip() for item in items if item.get(field)}

    with open(source, encoding="utf-8") as f:
        return _from_csv_text(f.read())


def filter_against_existing(places: list[dict], existing_keys: set[str], field: str = "place_id") -> list[dict]:
    """Remove places whose `field` value is in `existing_keys`."""
    if not existing_keys:
        return places
    return [p for p in places if str(p.get(field, "")).strip() not in existing_keys]
