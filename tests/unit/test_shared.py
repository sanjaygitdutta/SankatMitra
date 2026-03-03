"""
SankatMitra – Unit Tests for Shared Backend Modules
Tests all core functions in geo_utils and anomaly_detector.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from backend.shared.models import (
    GPSCoordinate, GPSData, CellTowerInfo,
    SpoofingFlagType, SpoofingRecommendation
)
from backend.shared.geo_utils import (
    haversine_distance, is_within_corridor, calculate_speed_kmph,
    calculate_acceleration_ms2, bearing_degrees
)
from backend.shared.anomaly_detector import (
    validate_gps_signal, compute_confidence_score, _check_impossible_speed,
    _check_location_jump, _check_signal_anomaly, _check_cell_mismatch
)
from backend.shared.security import create_access_token, verify_token, extract_vehicle_id


def _coord(lat: float, lon: float, dt: datetime = None) -> GPSCoordinate:
    return GPSCoordinate(
        latitude=lat,
        longitude=lon,
        accuracy=5.0,
        timestamp=dt or datetime.now(timezone.utc),
    )


# ===========================================================================
# GEO UTILS TESTS
# ===========================================================================

class TestHaversineDistance:
    def test_same_point_is_zero(self):
        c = _coord(19.076, 72.877)
        assert haversine_distance(c, c) == pytest.approx(0.0, abs=0.01)

    def test_known_distance_mumbai_to_pune(self):
        mumbai = _coord(19.076, 72.877)
        pune = _coord(18.520, 73.854)
        dist = haversine_distance(mumbai, pune)
        assert 110_000 < dist < 130_000  # ~119.9 km (crow flies)

    def test_symmetric(self):
        a = _coord(19.0, 72.8)
        b = _coord(18.5, 73.5)
        assert haversine_distance(a, b) == pytest.approx(haversine_distance(b, a), rel=1e-6)


class TestIsWithinCorridor:
    def test_vehicle_on_route_is_alerted(self):
        route = [_coord(19.0, 72.8), _coord(19.0, 72.9)]
        vehicle = _coord(19.0005, 72.85)  # very close to route midpoint
        assert is_within_corridor(vehicle, route, radius_meters=500) is True

    def test_vehicle_far_away_not_alerted(self):
        route = [_coord(19.0, 72.8), _coord(19.0, 72.9)]
        vehicle = _coord(19.01, 73.5)  # far away
        assert is_within_corridor(vehicle, route, radius_meters=500) is False

    def test_single_waypoint(self):
        route = [_coord(19.0, 72.8)]
        vehicle = _coord(19.0, 72.8)
        assert is_within_corridor(vehicle, route, radius_meters=500) is True

    def test_empty_route(self):
        assert is_within_corridor(_coord(19.0, 72.8), [], radius_meters=500) is False


class TestSpeedCalculation:
    def test_stationary(self):
        t = datetime.now(timezone.utc)
        c1 = _coord(19.0, 72.8, t)
        c2 = _coord(19.0, 72.8, t)
        assert calculate_speed_kmph(c1, c2) == 0.0

    def test_reasonable_ambulance_speed(self):
        t = datetime.now(timezone.utc)
        # Move ~138 m in 10 seconds = ~50 km/h
        c1 = _coord(19.0000, 72.8000, t)
        c2 = _coord(19.0012, 72.8000, t + timedelta(seconds=10))
        speed = calculate_speed_kmph(c1, c2)
        assert 40 < speed < 60


# ===========================================================================
# ANOMALY DETECTOR TESTS
# ===========================================================================

class TestImpossibleSpeedCheck:
    def test_normal_speed_passes(self):
        t = datetime.now(timezone.utc)
        prev = _coord(19.0, 72.8, t)
        curr = _coord(19.001, 72.8, t + timedelta(seconds=5))
        flag = _check_impossible_speed(curr, prev, max_speed_kmph=150.0)
        assert flag is None

    def test_impossible_speed_flagged(self):
        t = datetime.now(timezone.utc)
        prev = _coord(19.0, 72.8, t)
        # teleport 100 km in 1 second
        curr = _coord(19.9, 72.8, t + timedelta(seconds=1))
        flag = _check_impossible_speed(curr, prev, max_speed_kmph=150.0)
        assert flag is not None
        assert flag.type == SpoofingFlagType.IMPOSSIBLE_SPEED

    def test_no_previous_always_passes(self):
        curr = _coord(19.0, 72.8)
        flag = _check_impossible_speed(curr, None, max_speed_kmph=150.0)
        assert flag is None


class TestLocationJumpCheck:
    def test_normal_movement_passes(self):
        t = datetime.now(timezone.utc)
        h = [_coord(19.0, 72.8, t)]
        curr = _coord(19.001, 72.8, t + timedelta(seconds=5))
        flag = _check_location_jump(curr, h)
        assert flag is None

    def test_massive_jump_flagged(self):
        t = datetime.now(timezone.utc)
        h = [_coord(19.0, 72.8, t)]
        curr = _coord(20.5, 72.8, t + timedelta(seconds=5))  # ~166 km jump
        flag = _check_location_jump(curr, h)
        assert flag is not None
        assert flag.type == SpoofingFlagType.LOCATION_JUMP


class TestSignalAnomalyCheck:
    def test_good_signal_passes(self):
        coord = _coord(19.0, 72.8)
        gps_data = GPSData(
            coordinate=coord, satellite_count=8, signal_strength=-75.0
        )
        flag = _check_signal_anomaly(gps_data)
        assert flag is None

    def test_low_satellite_count_flagged(self):
        coord = _coord(19.0, 72.8)
        gps_data = GPSData(
            coordinate=coord, satellite_count=2, signal_strength=-75.0
        )
        flag = _check_signal_anomaly(gps_data)
        assert flag is not None
        assert flag.type == SpoofingFlagType.SIGNAL_ANOMALY


class TestValidateGpsSignal:
    def test_clean_signal_accepted(self):
        t = datetime.now(timezone.utc)
        history = [_coord(19.0, 72.8, t - timedelta(seconds=2))]
        current = _coord(19.0005, 72.8, t)
        gps_data = GPSData(
            coordinate=current, satellite_count=9, signal_strength=-70.0
        )
        result = validate_gps_signal(gps_data, history)
        assert result.is_valid is True
        assert result.confidence_score >= 0.95
        assert result.recommendation == SpoofingRecommendation.ACCEPT

    def test_teleport_rejected(self):
        t = datetime.now(timezone.utc)
        history = [_coord(19.0, 72.8, t - timedelta(seconds=2))]
        current = _coord(21.0, 72.8, t)  # 222 km jump
        gps_data = GPSData(
            coordinate=current, satellite_count=8, signal_strength=-70.0
        )
        result = validate_gps_signal(gps_data, history)
        assert result.confidence_score < 0.95
        assert result.is_valid is False
        assert result.recommendation in (
            SpoofingRecommendation.REJECT, SpoofingRecommendation.REVIEW
        )


# ===========================================================================
# SECURITY / JWT TESTS
# ===========================================================================

class TestJWTSecurity:
    def test_create_and_verify_token(self):
        token, expires_at = create_access_token("AMB-001")
        payload = verify_token(token)
        assert payload["sub"] == "AMB-001"
        assert payload["vehicle_type"] == "AMBULANCE"

    def test_invalid_token_raises(self):
        with pytest.raises(Exception):
            verify_token("not.a.valid.token")

    def test_extract_vehicle_id(self):
        token, _ = create_access_token("AMB-002")
        assert extract_vehicle_id(token) == "AMB-002"

    def test_extract_from_bad_token_returns_none(self):
        assert extract_vehicle_id("bad_token") is None
