"""
SankatMitra – Geo-spatial Utilities
Haversine distance and geospatial buffer calculations.
(Zero-Dependency Version)
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import List, Tuple, Any

# Earth radius in metres
_EARTH_RADIUS_M = 6_371_000.0


def _get_dt(ts: Any) -> datetime:
    """Helper to ensure we have a datetime object for calculations."""
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except:
            return datetime.utcnow()
    return datetime.utcnow()


def _get_coord_val(obj: Any, key: str, default: float = 0.0) -> float:
    """Safely get a coordinate value from either an object or a dict."""
    if hasattr(obj, key):
        val = getattr(obj, key)
        return float(val) if val is not None else default
    if isinstance(obj, dict):
        val = obj.get(key)
        return float(val) if val is not None else default
    return default


def haversine_distance(a: Any, b: Any) -> float:
    lat1 = math.radians(_get_coord_val(a, 'latitude'))
    lon1 = math.radians(_get_coord_val(a, 'longitude'))
    lat2 = math.radians(_get_coord_val(b, 'latitude'))
    lon2 = math.radians(_get_coord_val(b, 'longitude'))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def point_to_segment_distance(point: Any, seg_start: Any, seg_end: Any) -> float:
    p_lat = _get_coord_val(point, 'latitude')
    p_lon = _get_coord_val(point, 'longitude')
    s_lat = _get_coord_val(seg_start, 'latitude')
    s_lon = _get_coord_val(seg_start, 'longitude')
    e_lat = _get_coord_val(seg_end, 'latitude')
    e_lon = _get_coord_val(seg_end, 'longitude')

    def to_xy(lat, lon):
        x = math.radians(lon - s_lon) * _EARTH_RADIUS_M * math.cos(math.radians(s_lat))
        y = math.radians(lat - s_lat) * _EARTH_RADIUS_M
        return x, y

    px, py = to_xy(p_lat, p_lon)
    ex, ey = to_xy(e_lat, e_lon)

    seg_len_sq = ex * ex + ey * ey
    if seg_len_sq == 0:
        return math.sqrt(px * px + py * py)

    t = max(0.0, min(1.0, (px * ex + py * ey) / seg_len_sq))
    nearest_x = t * ex
    nearest_y = t * ey
    dx, dy = px - nearest_x, py - nearest_y
    return math.sqrt(dx * dx + dy * dy)


def is_within_corridor(
    vehicle_location: Any,
    route_waypoints: List[Any],
    radius_meters: float = 500.0,
) -> bool:
    if len(route_waypoints) < 2:
        if route_waypoints:
            return haversine_distance(vehicle_location, route_waypoints[0]) <= radius_meters
        return False

    for i in range(len(route_waypoints) - 1):
        dist = point_to_segment_distance(vehicle_location, route_waypoints[i], route_waypoints[i + 1])
        if dist <= radius_meters:
            return True
    return False


def calculate_speed_kmph(loc1: Any, loc2: Any) -> float:
    distance_m = haversine_distance(loc1, loc2)
    
    def _get_ts(obj):
        if hasattr(obj, 'timestamp'): return getattr(obj, 'timestamp')
        if isinstance(obj, dict): return obj.get('timestamp')
        return None

    t1 = _get_dt(_get_ts(loc1))
    t2 = _get_dt(_get_ts(loc2))
    
    dt_seconds = abs((t2 - t1).total_seconds())
    if dt_seconds == 0:
        return 0.0
    return (distance_m / dt_seconds) * 3.6


def bearing_degrees(a: Any, b: Any) -> float:
    lat1 = math.radians(_get_coord_val(a, 'latitude'))
    lon1 = math.radians(_get_coord_val(a, 'longitude'))
    lat2 = math.radians(_get_coord_val(b, 'latitude'))
    lon2 = math.radians(_get_coord_val(b, 'longitude'))
    
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360
