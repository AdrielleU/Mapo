"""Geographic helpers — bounding-box / polygon → grid expansion.

Used by the pipeline to fan out a single job into N sub-tasks, one per grid
cell, when the user supplies `grid_bbox` or `geo_polygon`. Each sub-task gets
a `coordinates: "lat,lon"` (cell center) and Google Maps biases its results
to that region. With small enough cells this gives near-exhaustive coverage
of an arbitrary area, which is necessary because Google caps a single search
to ~120 results.
"""

from __future__ import annotations

import math


EARTH_KM_PER_DEG_LAT = 111.32  # roughly constant


def km_to_deg_lat(km: float) -> float:
    return km / EARTH_KM_PER_DEG_LAT


def km_to_deg_lon(km: float, at_lat: float) -> float:
    """Longitude degrees per km vary with latitude (cos shrinkage)."""
    cos_lat = max(math.cos(math.radians(at_lat)), 1e-6)
    return km / (EARTH_KM_PER_DEG_LAT * cos_lat)


def cell_side_to_zoom(km: float) -> float:
    """Pick a Google Maps zoom level that roughly matches a cell side length.

    Empirical: at the equator, zoom 14 covers ~3 km, zoom 13 ~6 km, zoom 12 ~12 km.
    """
    if km <= 1.5:
        return 16
    if km <= 3:
        return 15
    if km <= 6:
        return 14
    if km <= 12:
        return 13
    if km <= 25:
        return 12
    if km <= 50:
        return 11
    return 10


def bbox_to_grid(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float, cell_km: float
) -> list[tuple[float, float]]:
    """Tile a bounding box into a grid; return a list of (lat, lon) cell centers.

    Cell size is approximate — we use the latitude midpoint to convert km → deg
    longitude, so cells near the poles will be slightly distorted.
    """
    if min_lat > max_lat or min_lon > max_lon:
        raise ValueError("bbox is inverted (min must be <= max)")
    if cell_km <= 0:
        raise ValueError("cell_km must be positive")

    mid_lat = (min_lat + max_lat) / 2
    d_lat = km_to_deg_lat(cell_km)
    d_lon = km_to_deg_lon(cell_km, mid_lat)

    cells: list[tuple[float, float]] = []
    lat = min_lat + d_lat / 2
    while lat < max_lat + d_lat / 2:
        lon = min_lon + d_lon / 2
        while lon < max_lon + d_lon / 2:
            cells.append((round(lat, 6), round(lon, 6)))
            lon += d_lon
        lat += d_lat
    return cells


def point_in_polygon(lat: float, lon: float, polygon: list[list[float]]) -> bool:
    """Ray-casting test. Polygon points are [lat, lon] pairs (outer ring only)."""
    if len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i][0], polygon[i][1]
        lat_j, lon_j = polygon[j][0], polygon[j][1]
        intersects = ((lat_i > lat) != (lat_j > lat)) and (
            lon < (lon_j - lon_i) * (lat - lat_i) / ((lat_j - lat_i) or 1e-12) + lon_i
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def polygon_to_grid(polygon: list[list[float]], cell_km: float) -> list[tuple[float, float]]:
    """Generate a grid covering the polygon's bbox, then drop cells outside the polygon."""
    if not polygon:
        return []
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    bbox_cells = bbox_to_grid(min(lats), min(lons), max(lats), max(lons), cell_km)
    return [(la, lo) for la, lo in bbox_cells if point_in_polygon(la, lo, polygon)]
