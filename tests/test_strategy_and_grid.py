"""Tests for the strategy preset + grid expansion in split_task_by_query."""

import pytest

from backend.server import _apply_strategy, _expand_geo_grid, split_task_by_query


def test_strategy_fastest_sets_max_results_when_default():
    out = _apply_strategy({"strategy": "fastest", "max_results": 100})
    assert out["max_results"] == 21


def test_strategy_does_not_override_explicit_max_results():
    out = _apply_strategy({"strategy": "fastest", "max_results": 500})
    assert out["max_results"] == 500


def test_strategy_detailed_enables_reviews():
    out = _apply_strategy({"strategy": "detailed", "max_results": 100})
    assert out["enable_reviews"] is True


def test_strategy_unknown_is_noop():
    src = {"strategy": "made-up", "max_results": 100}
    assert _apply_strategy(src) == src


def test_strategy_empty_is_noop():
    src = {"max_results": 100}
    assert _apply_strategy(src) == src


def test_expand_geo_grid_no_geo_returns_none():
    assert _expand_geo_grid({"query": "pizza"}) is None


def test_expand_geo_grid_bbox_produces_subtasks():
    tasks = _expand_geo_grid({
        "query": "coffee",
        "grid_bbox": [40.70, -74.02, 40.80, -73.92],
        "grid_cell_km": 10.0,
    })
    assert tasks is not None
    assert len(tasks) >= 1
    for t in tasks:
        assert t["query"] == "coffee"
        assert "," in t["coordinates"]
        assert isinstance(t["zoom_level"], (int, float))


def test_expand_geo_grid_polygon_produces_subtasks():
    tasks = _expand_geo_grid({
        "query": "coffee",
        "geo_polygon": [[40.70, -74.02], [40.80, -74.02], [40.75, -73.92]],
        "grid_cell_km": 2.0,
    })
    assert tasks and len(tasks) >= 3


def test_expand_geo_grid_requires_query_or_business_type():
    with pytest.raises(ValueError):
        _expand_geo_grid({"grid_bbox": [0, 0, 1, 1], "grid_cell_km": 50.0})


def test_expand_geo_grid_uses_business_type_fallback():
    tasks = _expand_geo_grid({
        "business_type": "dentist",
        "grid_bbox": [40.70, -74.02, 40.80, -73.92],
        "grid_cell_km": 10.0,
    })
    assert tasks and tasks[0]["query"] == "dentist"


def test_expand_geo_grid_invalid_bbox_length():
    with pytest.raises(ValueError):
        _expand_geo_grid({"query": "x", "grid_bbox": [0, 0, 1]})


def test_split_task_by_query_uses_grid_when_set():
    """End-to-end: split_task_by_query routes through _expand_geo_grid when bbox present."""
    tasks = split_task_by_query({
        "query": "pizza",
        "grid_bbox": [40.70, -74.02, 40.80, -73.92],
        "grid_cell_km": 10.0,
    })
    assert all("coordinates" in t for t in tasks)
    assert all(t["query"] == "pizza" for t in tasks)
