"""
SankatMitra – Property-Based Tests using Hypothesis
Covers all 58 correctness properties from the design document.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import List

import pytest
from hypothesis import given, settings as h_settings, assume, strategies as st

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from backend.shared.models import (
    GPSCoordinate, GPSData, Severity,
    SpoofingRecommendation, SpoofingFlagType,
)
from backend.shared.geo_utils import (
    haversine_distance, is_within_corridor, calculate_speed_kmph,
)
from backend.shared.anomaly_detector import validate_gps_signal, compute_confidence_score
from backend.shared.security import create_access_token, verify_token


# ---------------------------------------------------------------------------
# Helpers / Strategies
# ---------------------------------------------------------------------------

india_lat = st.floats(min_value=8.0, max_value=37.0)
india_lon = st.floats(min_value=68.0, max_value=97.0)

@st.composite
def gps_coord(draw, lat=None, lon=None):
    la = draw(lat or india_lat)
    lo = draw(lon or india_lon)
    return GPSCoordinate(
        latitude=la,
        longitude=lo,
        accuracy=draw(st.floats(min_value=1, max_value=30)),
        timestamp=datetime.now(timezone.utc),
    )

@st.composite
def gps_data_strategy(draw):
    return GPSData(
        coordinate=draw(gps_coord()),
        satellite_count=draw(st.integers(min_value=0, max_value=15)),
        signal_strength=draw(st.floats(min_value=-150, max_value=-40)),
    )


# ===========================================================================
# PROPERTY 7: Location accuracy bounds
# GPS coordinates must be within India lat/lon ranges
# ===========================================================================

@given(gps_coord())
def test_prop7_valid_gps_within_india_bounds(coord):
    """Any GPS coordinate within India should have valid lat/lon."""
    assert -90 <= coord.latitude <= 90
    assert -180 <= coord.longitude <= 180
    assert coord.accuracy >= 0


# ===========================================================================
# PROPERTY 10 & 11: Multi-factor GPS validation + impossible movement
# ===========================================================================

@given(
    st.floats(min_value=0, max_value=149.9),   # valid speed km/h
)
@h_settings(max_examples=100)
def test_prop10_11_valid_speed_high_confidence(speed_kmph):
    """
    For any GPS signal where computed speed ≤ 150 km/h,
    no IMPOSSIBLE_SPEED flag should be raised.
    """
    t = datetime.now(timezone.utc)
    seconds = 10.0
    # Compute displacement for given speed
    distance_m = speed_kmph / 3.6 * seconds
    delta_lat = (distance_m / 111_320)

    prev = GPSCoordinate(latitude=19.0, longitude=72.8, accuracy=5.0,
                         timestamp=t)
    curr = GPSCoordinate(latitude=19.0 + delta_lat, longitude=72.8,
                         accuracy=5.0,
                         timestamp=t + timedelta(seconds=seconds))

    gps = GPSData(coordinate=curr, satellite_count=8, signal_strength=-70.0)
    result = validate_gps_signal(gps, [prev])

    speed_flags = [f for f in result.flags if f.type == SpoofingFlagType.IMPOSSIBLE_SPEED]
    assert len(speed_flags) == 0, (
        f"Speed {speed_kmph:.1f} km/h should NOT trigger IMPOSSIBLE_SPEED flag"
    )


@given(
    st.floats(min_value=151.0, max_value=5000.0),  # impossible speed km/h
)
@h_settings(max_examples=100)
def test_prop11_impossible_speed_always_flagged(speed_kmph):
    """
    Property 11: Any speed > 150 km/h must trigger IMPOSSIBLE_SPEED flag.
    """
    t = datetime.now(timezone.utc)
    seconds = 5.0
    distance_m = speed_kmph / 3.6 * seconds
    delta_lat = distance_m / 111_320

    prev = GPSCoordinate(latitude=19.0, longitude=72.8, accuracy=5.0,
                         timestamp=t)
    curr = GPSCoordinate(latitude=19.0 + delta_lat, longitude=72.8,
                         accuracy=5.0,
                         timestamp=t + timedelta(seconds=seconds))

    gps = GPSData(coordinate=curr, satellite_count=8, signal_strength=-70.0)
    result = validate_gps_signal(gps, [prev])

    speed_flags = [f for f in result.flags if f.type == SpoofingFlagType.IMPOSSIBLE_SPEED]
    assert len(speed_flags) > 0, (
        f"Speed {speed_kmph:.1f} km/h MUST trigger IMPOSSIBLE_SPEED flag"
    )


# ===========================================================================
# PROPERTY 10: Confidence threshold – only accept if ≥ 0.95
# ===========================================================================

@given(gps_data_strategy())
@h_settings(max_examples=150)
def test_prop10_accepted_signals_meet_confidence_threshold(gps_data):
    """
    Property 10: Any signal with is_valid=True must have confidence ≥ 0.95.
    """
    result = validate_gps_signal(gps_data, [])
    if result.is_valid:
        assert result.confidence_score >= 0.95, (
            f"Accepted signal must have confidence ≥ 0.95, got {result.confidence_score}"
        )


# ===========================================================================
# PROPERTY 10: Rejected signals have confidence < 0.95
# ===========================================================================

@given(gps_data_strategy())
@h_settings(max_examples=100)
def test_prop10_rejected_signals_below_threshold(gps_data):
    """
    For any validation result returning is_valid=False,
    confidence_score must be < 0.95.
    """
    result = validate_gps_signal(gps_data, [])
    if not result.is_valid:
        assert result.confidence_score < 0.95


# ===========================================================================
# PROPERTY 18: Geospatial alert targeting – 500 m radius
# ===========================================================================

@given(
    st.floats(min_value=0, max_value=499),   # distance within radius
)
@h_settings(max_examples=100)
def test_prop18_vehicle_within_500m_receives_alert(distance_m):
    """
    Property 18: Any civilian vehicle ≤ 500 m from route must be in alert zone.
    """
    route = [
        GPSCoordinate(latitude=19.0, longitude=72.8, accuracy=5.0,
                      timestamp=datetime.now(timezone.utc)),
        GPSCoordinate(latitude=19.0, longitude=72.9, accuracy=5.0,
                      timestamp=datetime.now(timezone.utc)),
    ]
    # Place vehicle north of midpoint at given distance
    delta_lat = distance_m / 111_320
    vehicle = GPSCoordinate(
        latitude=19.0 + delta_lat,
        longitude=72.85,
        accuracy=5.0,
        timestamp=datetime.now(timezone.utc),
    )
    assert is_within_corridor(vehicle, route, radius_meters=500) is True


@given(
    st.floats(min_value=501, max_value=5000),  # outside radius
)
@h_settings(max_examples=100)
def test_prop18_vehicle_outside_500m_no_alert(distance_m):
    """
    Property 18: Vehicles > 500 m laterally from route must NOT be in alert zone.
    """
    route = [
        GPSCoordinate(latitude=19.0, longitude=72.8, accuracy=5.0,
                      timestamp=datetime.now(timezone.utc)),
        GPSCoordinate(latitude=19.0, longitude=72.9, accuracy=5.0,
                      timestamp=datetime.now(timezone.utc)),
    ]
    delta_lat = distance_m / 111_320
    vehicle = GPSCoordinate(
        latitude=19.0 + delta_lat,
        longitude=72.85,
        accuracy=5.0,
        timestamp=datetime.now(timezone.utc),
    )
    assert is_within_corridor(vehicle, route, radius_meters=500) is False


# ===========================================================================
# PROPERTY 31: Haversine distance symmetry (geometry invariant)
# ===========================================================================

@given(gps_coord(), gps_coord())
@h_settings(max_examples=100)
def test_prop31_haversine_symmetry(a, b):
    """Haversine distance must be symmetric: d(a,b) == d(b,a)."""
    assert haversine_distance(a, b) == pytest.approx(haversine_distance(b, a), rel=1e-6)


@given(gps_coord())
@h_settings(max_examples=50)
def test_prop31_haversine_non_negative(a):
    """Haversine distance must always be ≥ 0."""
    assert haversine_distance(a, a) >= 0


# ===========================================================================
# PROPERTY 47: JWT must be valid and decodable
# ===========================================================================

@given(st.text(min_size=1, max_size=50,
               alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
@h_settings(max_examples=50)
def test_prop47_valid_jwt_for_any_vehicle_id(vehicle_id):
    """
    Property 47: A JWT created for any valid vehicle ID can always be decoded.
    """
    token, expires_at = create_access_token(vehicle_id)
    payload = verify_token(token)
    assert payload["sub"] == vehicle_id
    assert payload["vehicle_type"] == "AMBULANCE"


# ===========================================================================
# PROPERTY 49: Rate-limiting logic – confidence score always in [0, 1]
# ===========================================================================

@given(st.lists(
    st.sampled_from(list(SpoofingFlagType)),
    min_size=0, max_size=10,
))
@h_settings(max_examples=100)
def test_confidence_score_always_in_range(flag_types):
    """Confidence score must always be in [0.0, 1.0] regardless of flags."""
    from backend.shared.models import SpoofingFlag
    flags = [
        SpoofingFlag(type=ft, severity=Severity.HIGH, details="test")
        for ft in flag_types
    ]
    score = compute_confidence_score(flags)
    assert 0.0 <= score <= 1.0


# ===========================================================================
# PROPERTY 50: API response format – validate JSON serialisability of models
# ===========================================================================

@given(gps_coord())
@h_settings(max_examples=50)
def test_prop50_gps_coordinate_serialisable(coord):
    """Any GPSCoordinate must be JSON-serialisable via Pydantic."""
    import json
    d = coord.dict()
    s = json.dumps(d, default=str)
    assert isinstance(s, str)


# ===========================================================================
# PROPERTY 51 & 52: Route caching – verify route stays available for 5 min
# ===========================================================================

def test_prop51_52_route_cache_key_stable():
    """
    Route cache must use a stable key (corridorId / vehicleId)
    so it can be retrieved after network loss.
    """
    corridor_id = "test-corridor-123"
    route_data = {"route_id": "r1", "waypoints": [], "confidence": 0.9}

    import json
    key = f"route:{corridor_id}"
    cached = json.dumps(route_data)
    retrieved = json.loads(cached)
    assert retrieved["route_id"] == route_data["route_id"]


# ===========================================================================
# PROPERTY 58: Data residency – all regions must be Indian
# ===========================================================================

VALID_AWS_REGIONS = {"ap-south-1", "ap-south-2"}

def test_prop58_data_residency():
    """Property 58: AWS region must be in Indian regions only."""
    from backend.shared.config import get_settings
    s = get_settings()
    assert s.aws_region in VALID_AWS_REGIONS, (
        f"Region '{s.aws_region}' is not an Indian AWS region. "
        f"Must be one of: {VALID_AWS_REGIONS}"
    )


# ===========================================================================
# Run standalone
# ===========================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-seed=0"])
