"""
Result filtering and field ordering utilities.
"""


def filter_places(places, criteria):
    """
    Filter a list of places by criteria.

    Supported criteria:
        has_website: bool - filter by website presence
        min_reviews: int - minimum review count
    """
    def matches(place):
        has_website = criteria.get("has_website")
        if has_website is not None:
            website = place.get("website")
            if has_website and website is None:
                return False
            if not has_website and website is not None:
                return False

        min_reviews = criteria.get("min_reviews")
        if min_reviews is not None:
            reviews = place.get("reviews")
            if reviews is None or reviews == "" or reviews < min_reviews:
                return False

        return True

    return [p for p in places if matches(p)]


def sort_dict_by_keys(dictionary, keys):
    """Reorder dict keys to match a canonical field order."""
    return {key: dictionary[key] for key in keys if key in dictionary}
