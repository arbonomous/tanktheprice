"""Geospatial geometry and corridor definitions for the Strait of Hormuz."""

from __future__ import annotations

import math
from typing import Iterable, Tuple

# Primary Strait of Hormuz monitoring bounding box
STRAIT_BBOX = {
    "lat_min": 24.0,
    "lat_max": 28.0,
    "lon_min": 55.0,
    "lon_max": 58.5,
}

# High-sensitivity AIS-dark / dark-fleet corridor
DARK_CORRIDOR_BBOX = {
    "lat_min": 25.5,
    "lat_max": 27.0,
    "lon_min": 55.8,
    "lon_max": 57.0,
}

# Reference chokepoint center (used for Datalastic radius queries)
CHOKEPOINT_CENTER = (26.566, 56.25)

# Designated anchorages (lon, lat) bounding boxes where low speed is normal
DESIGNATED_ANCHORAGES = {
    "fujairah": {"lat_min": 25.00, "lat_max": 25.28, "lon_min": 56.37, "lon_max": 56.56},
    "khor_fakkan": {"lat_min": 25.30, "lat_max": 25.44, "lon_min": 56.38, "lon_max": 56.52},
    "bandar_abbas": {"lat_min": 27.04, "lat_max": 27.16, "lon_min": 56.14, "lon_max": 56.36},
    "jebel_ali_outer": {"lat_min": 25.02, "lat_max": 25.18, "lon_min": 55.00, "lon_max": 55.16},
}

# Congestion watch hubs (center lat, center lon, watch radius in nautical miles)
CONGESTION_HUBS = {
    "fujairah": (25.13, 56.47, 28.0),
    "bandar_abbas": (27.10, 56.25, 25.0),
    "musandam_tss": (26.42, 56.45, 22.0),
}

# Traffic Separation Scheme (TSS) polygons as (lon, lat) vertices
TSS_OUTBOUND_POLY: list[Tuple[float, float]] = [
    (55.45, 25.95),
    (56.05, 26.25),
    (56.48, 26.35),
    (56.78, 26.05),
    (57.25, 25.40),
    (57.00, 25.25),
    (56.58, 25.88),
    (56.35, 26.15),
    (55.98, 26.08),
    (55.45, 25.78),
]

TSS_INBOUND_POLY: list[Tuple[float, float]] = [
    (55.35, 26.28),
    (56.10, 26.62),
    (56.68, 26.62),
    (57.15, 26.20),
    (57.62, 25.65),
    (57.38, 25.48),
    (56.92, 26.02),
    (56.55, 26.42),
    (56.08, 26.42),
    (55.35, 26.10),
]

# Waypoint spines (lat, lon) for realistic shipping lane positioning
OUTBOUND_LANE_SPINE: list[Tuple[float, float]] = [
    (26.10, 55.20),
    (26.22, 55.75),
    (26.32, 56.22),
    (26.28, 56.50),
    (25.92, 56.78),
    (25.45, 57.12),
    (24.95, 57.60),
    (24.55, 58.15),
]

INBOUND_LANE_SPINE: list[Tuple[float, float]] = [
    (24.85, 58.25),
    (25.35, 57.68),
    (25.88, 57.18),
    (26.38, 56.74),
    (26.55, 56.38),
    (26.50, 55.92),
    (26.34, 55.42),
    (26.25, 55.12),
]


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in nautical miles between two WGS84 coordinates."""
    r_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * r_nm * math.asin(min(1.0, math.sqrt(a)))


def point_in_polygon(lon: float, lat: float, polygon: Iterable[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon check for (lon, lat) coordinates."""
    pts = list(polygon)
    inside = False
    n = len(pts)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        intersect = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) + 1e-12) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def is_in_strait(lat: float, lon: float) -> bool:
    return (
        STRAIT_BBOX["lat_min"] <= lat <= STRAIT_BBOX["lat_max"]
        and STRAIT_BBOX["lon_min"] <= lon <= STRAIT_BBOX["lon_max"]
    )


def is_in_dark_corridor(lat: float, lon: float) -> bool:
    return (
        DARK_CORRIDOR_BBOX["lat_min"] <= lat <= DARK_CORRIDOR_BBOX["lat_max"]
        and DARK_CORRIDOR_BBOX["lon_min"] <= lon <= DARK_CORRIDOR_BBOX["lon_max"]
    )


def is_in_designated_anchorage(lat: float, lon: float) -> bool:
    for box in DESIGNATED_ANCHORAGES.values():
        if (
            box["lat_min"] <= lat <= box["lat_max"]
            and box["lon_min"] <= lon <= box["lon_max"]
        ):
            return True
    return False


def is_in_tss_lane(lat: float, lon: float) -> bool:
    return point_in_polygon(lon, lat, TSS_OUTBOUND_POLY) or point_in_polygon(lon, lat, TSS_INBOUND_POLY)


def is_congestion_loitering(lat: float, lon: float, speed_knots: float) -> bool:
    """Flag tankers idling (< 3 knots) near Fujairah, Bandar Abbas, or inside TSS outside anchorages."""
    if speed_knots >= 3.0:
        return False
    if is_in_designated_anchorage(lat, lon):
        return False
    if is_in_tss_lane(lat, lon):
        return True
    for _, (clat, clon, radius_nm) in CONGESTION_HUBS.items():
        if haversine_nm(lat, lon, clat, clon) <= radius_nm:
            return True
    return False


def is_outbound_laden(heading: float, draft_m: float) -> bool:
    """Check if tanker meets laden outbound exit criteria toward Gulf of Oman."""
    h = heading % 360.0
    return 90.0 <= h <= 160.0 and draft_m > 12.0
