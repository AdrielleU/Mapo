"""Tests for backend.scrapers.filters"""
import csv
import json
import os
import tempfile

import pytest

from backend.scrapers.filters import (
    filter_places,
    sort_dict_by_keys,
    load_existing_keys,
    filter_against_existing,
)


@pytest.fixture
def sample_places():
    return [
        {"name": "Open Quality", "rating": 4.5, "reviews": 100, "phone": "555-1", "website": "http://a.com",
         "is_permanently_closed": False, "is_temporarily_closed": False,
         "categories": ["Restaurant"], "price_range": "$$", "place_id": "id1"},
        {"name": "Closed Shop", "rating": 3.0, "reviews": 5, "phone": None, "website": None,
         "is_permanently_closed": True, "is_temporarily_closed": False,
         "categories": ["Store"], "place_id": "id2"},
        {"name": "Low Rating", "rating": 2.0, "reviews": 200, "phone": "555-2", "website": "http://b.com",
         "is_permanently_closed": False, "is_temporarily_closed": False,
         "categories": ["Bar"], "place_id": "id3"},
        {"name": "No Phone", "rating": 4.8, "reviews": 50, "phone": None, "website": "http://c.com",
         "is_permanently_closed": False, "is_temporarily_closed": False,
         "categories": ["Cafe"], "place_id": "id4"},
    ]


def test_filter_skip_closed(sample_places):
    result = filter_places(sample_places, {"skip_closed": True})
    names = [p["name"] for p in result]
    assert "Closed Shop" not in names
    assert len(result) == 3


def test_filter_min_rating(sample_places):
    result = filter_places(sample_places, {"min_rating": 4.0})
    assert all(p["rating"] >= 4.0 for p in result)
    assert len(result) == 2


def test_filter_has_phone(sample_places):
    result = filter_places(sample_places, {"has_phone": True})
    assert all(p["phone"] for p in result)
    assert len(result) == 2


def test_filter_has_website(sample_places):
    result = filter_places(sample_places, {"has_website": True})
    assert all(p["website"] for p in result)
    assert len(result) == 3


def test_filter_min_reviews(sample_places):
    result = filter_places(sample_places, {"min_reviews": 50})
    assert all(p["reviews"] >= 50 for p in result)
    assert len(result) == 3


def test_filter_combined(sample_places):
    result = filter_places(sample_places, {
        "skip_closed": True,
        "min_rating": 4.0,
        "has_phone": True,
    })
    assert len(result) == 1
    assert result[0]["name"] == "Open Quality"


def test_filter_category_in(sample_places):
    result = filter_places(sample_places, {"category_in": ["Restaurant", "Cafe"]})
    names = sorted(p["name"] for p in result)
    assert names == ["No Phone", "Open Quality"]


def test_filter_price_range(sample_places):
    result = filter_places(sample_places, {"price_range": "$$"})
    assert len(result) == 1
    assert result[0]["name"] == "Open Quality"


def test_filter_no_criteria_returns_all(sample_places):
    result = filter_places(sample_places, {})
    assert len(result) == len(sample_places)


def test_sort_dict_by_keys():
    data = {"c": 3, "a": 1, "b": 2}
    result = sort_dict_by_keys(data, ["a", "b", "c"])
    assert list(result.keys()) == ["a", "b", "c"]


def test_sort_dict_by_keys_skips_missing():
    data = {"a": 1, "c": 3}
    result = sort_dict_by_keys(data, ["a", "b", "c"])
    assert list(result.keys()) == ["a", "c"]


def test_load_existing_keys_from_csv(sample_places):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        writer = csv.DictWriter(f, fieldnames=["place_id", "name"])
        writer.writeheader()
        writer.writerow({"place_id": "id1", "name": "First"})
        writer.writerow({"place_id": "id2", "name": "Second"})
        path = f.name

    try:
        keys = load_existing_keys(path, "place_id")
        assert keys == {"id1", "id2"}
    finally:
        os.unlink(path)


def test_load_existing_keys_from_json():
    items = [{"place_id": "id1"}, {"place_id": "id2"}]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(items, f)
        path = f.name

    try:
        keys = load_existing_keys(path, "place_id")
        assert keys == {"id1", "id2"}
    finally:
        os.unlink(path)


def test_filter_against_existing(sample_places):
    existing = {"id1", "id3"}
    result = filter_against_existing(sample_places, existing, "place_id")
    names = sorted(p["name"] for p in result)
    assert names == ["Closed Shop", "No Phone"]


def test_filter_against_existing_empty_set_returns_all(sample_places):
    result = filter_against_existing(sample_places, set(), "place_id")
    assert len(result) == len(sample_places)
