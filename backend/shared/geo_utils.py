"""
SankatMitra – Geo-spatial Utilities
Haversine distance and geospatial buffer calculations.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from .models import GPSCoordinate

# Earth radius in metres
_EARTH_RADIUS_M = 6_371_000.0


def haversine_distance(a: GPSCoordinate, b: GPSCoordinate) -> float:
    """
    Calculate the great-circle distance between two GPS coordinates.

    Returns:
        Distance in metres.
    """
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def point_to_segment_distance(point: GPSCoordinate, seg_start: GPSCoordinate, seg_end: GPSCoordinate) -> float:
    """
    Minimum distance from `point` to the line segment [seg_start, seg_end].
    Uses approximate planar geometry (fine for small distances < 50 km).

    Returns:
        Distance in metres.
    """
    # Convert to local Cartesian (metres)
    def to_xy(coord: GPSCoordinate) -> Tuple[float, float]:
        x = math.radians(coord.longitude - seg_start.longitude) * _EARTH_RADIUS_M * math.cos(
            math.radians(seg_start.latitude)
        )
        y = math.radians(coord.latitude - seg_start.latitude) * _EARTH_RADIUS_M
        return x, y

    px, py = to_xy(point)
    ex, ey = to_xy(seg_end)

    seg_len_sq = ex * ex + ey * ey
    if seg_len_sq == 0:
        return math.sqrt(px * px + py * py)

    t = max(0.0, min(1.0, (px * ex + py * ey) / seg_len_sq))
    nearest_x = t * ex
    nearest_y = t * ey
    dx, dy = px - nearest_x, py - nearest_y
    return math.sqrt(dx * dx + dy * dy)


def is_within_corridor(
    vehicle_location: GPSCoordinate,
    route_waypoints: List[GPSCoordinate],
    radius_meters: float = 500.0,
) -> bool:
    """
    Check if a civilian vehicle is within `radius_meters` of any segment of the route.

    Returns:
        True if the vehicle should receive an alert.
    """
    if len(route_waypoints) < 2:
        if route_waypoints:
            return haversine_distance(vehicle_location, route_waypoints[0]) <= radius_meters
        return False

    for i in range(len(route_waypoints) - 1):
        dist = point_to_segment_distance(vehicle_location, route_waypoints[i], route_waypoints[i + 1])
        if dist <= radius_meters:
            return True
    return False


def calculate_speed_kmph(loc1: GPSCoordinate, loc2: GPSCoordinate) -> float:
    """
    Compute speed in km/h between two consecutive GPS fixes.
    Returns 0.0 if timestamps are identical.
    """
    distance_m = haversine_distance(loc1, loc2)
    dt_seconds = abs((loc2.timestamp - loc1.timestamp).total_seconds())
    if dt_seconds == 0:
        return 0.0
    return (distance_m / dt_seconds) * 3.6  # m/s → km/h


def calculate_acceleration_ms2(
    loc1: GPSCoordinate, loc2: GPSCoordinate, loc3: GPSCoordinate
) -> float:
    """
    Compute acceleration in m/s² from three consecutive GPS fixes.
    """
    v1_ms = calculate_speed_kmph(loc1, loc2) / 3.6
    v2_ms = calculate_speed_kmph(loc2, loc3) / 3.6
    dt = abs((loc3.timestamp - loc1.timestamp).total_seconds())
    if dt == 0:
        return 0.0
    return abs(v2_ms - v1_ms) / dt


def bearing_degrees(a: GPSCoordinate, b: GPSCoordinate) -> float:
    """Forward bearing from a to b in degrees [0, 360)."""
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360
