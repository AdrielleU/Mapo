"""Tests for backend.geo grid + polygon helpers."""

from backend.geo import (
    bbox_to_grid,
    cell_side_to_zoom,
    km_to_deg_lat,
    km_to_deg_lon,
    point_in_polygon,
    polygon_to_grid,
)


def test_km_to_deg_lat_constant():
    assert abs(km_to_deg_lat(111.32) - 1.0) < 1e-6


def test_km_to_deg_lon_shrinks_with_latitude():
    # Equator: 1 deg lon ≈ 111 km. At 60° lat, ≈ 55 km, so 1 km ≈ 0.018 deg.
    eq = km_to_deg_lon(1.0, at_lat=0.0)
    high = km_to_deg_lon(1.0, at_lat=60.0)
    assert high > eq * 1.5


def test_bbox_to_grid_count_matches_area():
    # 10x10 km bbox at the equator with 5km cells → 2x2 = 4 cells
    cells = bbox_to_grid(0.0, 0.0, km_to_deg_lat(10), km_to_deg_lon(10, 0.0), cell_km=5.0)
    assert 3 <= len(cells) <= 6  # rounding tolerance


def test_bbox_inverted_raises():
    import pytest
    with pytest.raises(ValueError):
        bbox_to_grid(10.0, 10.0, 0.0, 0.0, cell_km=1.0)


def test_zero_cell_km_raises():
    import pytest
    with pytest.raises(ValueError):
        bbox_to_grid(0.0, 0.0, 1.0, 1.0, cell_km=0.0)


def test_point_in_polygon_basic():
    triangle = [[0.0, 0.0], [10.0, 0.0], [5.0, 10.0]]
    assert point_in_polygon(5.0, 3.0, triangle) is True
    assert point_in_polygon(-1.0, 5.0, triangle) is False
    assert point_in_polygon(20.0, 5.0, triangle) is False


def test_point_in_polygon_short_polygon_returns_false():
    assert point_in_polygon(0.5, 0.5, [[0, 0], [1, 1]]) is False


def test_polygon_to_grid_drops_outside_cells():
    # Triangle in NYC area, 1km cells
    tri = [[40.70, -74.02], [40.80, -74.02], [40.75, -73.92]]
    cells = polygon_to_grid(tri, cell_km=1.5)
    # Every returned cell must lie inside the triangle
    assert all(point_in_polygon(la, lo, tri) for la, lo in cells)
    # And there should be at least a few
    assert len(cells) >= 5


def test_polygon_to_grid_empty_input():
    assert polygon_to_grid([], cell_km=1.0) == []


def test_zoom_mapping_is_monotonic():
    # Bigger cells → lower zoom (zoomed out)
    z1 = cell_side_to_zoom(1.0)
    z5 = cell_side_to_zoom(5.0)
    z25 = cell_side_to_zoom(25.0)
    assert z1 >= z5 >= z25
