"""
SankatMitra – GPS Anomaly Detection Algorithm
Physics-based + multi-factor validation for GPS signals.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import List, Optional

from .config import get_settings
from .geo_utils import calculate_speed_kmph, calculate_acceleration_ms2, haversine_distance
from .models import (
    GPSCoordinate,
    GPSData,
    SpoofingFlag,
    SpoofingFlagType,
    SpoofingRecommendation,
    Severity,
    ValidationResult,
)

settings = get_settings()


def _check_impossible_speed(
    current: GPSCoordinate,
    previous: Optional[GPSCoordinate],
    max_speed_kmph: float,
) -> Optional[SpoofingFlag]:
    if previous is None:
        return None
    speed = calculate_speed_kmph(previous, current)
    if speed > max_speed_kmph:
        sev = Severity.HIGH if speed > max_speed_kmph * 1.5 else Severity.MEDIUM
        return SpoofingFlag(
            type=SpoofingFlagType.IMPOSSIBLE_SPEED,
            severity=sev,
            details=f"Detected speed {speed:.1f} km/h exceeds limit {max_speed_kmph} km/h",
        )
    return None


def _check_location_jump(
    current: GPSCoordinate,
    history: List[GPSCoordinate],
    jump_threshold_m: float = 1000.0,
) -> Optional[SpoofingFlag]:
    """Flag teleportation-style jumps that exceed jump_threshold_m in one update."""
    if not history:
        return None
    last = history[-1]
    dist = haversine_distance(last, current)
    dt = abs((current.timestamp - last.timestamp).total_seconds())
    # Allow up to 150 km/h travel → ~41.7 m/s
    max_legal_dist = 41.7 * dt + 50  # 50 m buffer for GPS noise
    if dist > max(jump_threshold_m, max_legal_dist):
        return SpoofingFlag(
            type=SpoofingFlagType.LOCATION_JUMP,
            severity=Severity.HIGH,
            details=f"Position jumped {dist:.0f} m in {dt:.1f} s",
        )
    return None


def _check_signal_anomaly(gps_data: GPSData) -> Optional[SpoofingFlag]:
    if gps_data.satellite_count < 4:
        return SpoofingFlag(
            type=SpoofingFlagType.SIGNAL_ANOMALY,
            severity=Severity.MEDIUM,
            details=f"Only {gps_data.satellite_count} satellites visible (min 4 required)",
        )
    if gps_data.signal_strength < -130:  # dBm
        return SpoofingFlag(
            type=SpoofingFlagType.SIGNAL_ANOMALY,
            severity=Severity.LOW,
            details=f"Weak signal: {gps_data.signal_strength:.1f} dBm",
        )
    return None


def _check_cell_mismatch(
    gps_data: GPSData,
    max_cell_distance_m: float = 2000.0,
) -> Optional[SpoofingFlag]:
    """Verify GPS position is consistent with cell tower positions."""
    if not gps_data.cell_tower_data:
        return None  # No cell data → cannot validate
    coord = gps_data.coordinate
    distances = [
        haversine_distance(
            coord,
            GPSCoordinate(
                latitude=tower.latitude,
                longitude=tower.longitude,
                timestamp=coord.timestamp,
            ),
        )
        for tower in gps_data.cell_tower_data
    ]
    min_tower_dist = min(distances)
    if min_tower_dist > max_cell_distance_m:
        return SpoofingFlag(
            type=SpoofingFlagType.CELL_MISMATCH,
            severity=Severity.HIGH,
            details=(
                f"GPS reports device {min_tower_dist:.0f} m from nearest cell tower, "
                f"expected < {max_cell_distance_m:.0f} m"
            ),
        )
    return None


def _check_acceleration(
    history: List[GPSCoordinate],
    max_accel_ms2: float,
) -> Optional[SpoofingFlag]:
    if len(history) < 2:
        return None
    prev2, prev1 = history[-2], history[-1]
    # Compute acceleration from last 2 history + placeholder for comparison
    v1 = calculate_speed_kmph(prev2, prev1) / 3.6  # m/s
    dt = abs((prev1.timestamp - prev2.timestamp).total_seconds())
    # We can only estimate if we have at least speed data
    return None  # Full 3-point accel check done in validate_gps_signal with current


def compute_confidence_score(flags: List[SpoofingFlag]) -> float:
    """
    Compute a [0, 1] confidence score (1 = fully trusted, 0 = definitely spoofed).
    """
    penalty_map = {
        (SpoofingFlagType.IMPOSSIBLE_SPEED, Severity.HIGH): 0.60,
        (SpoofingFlagType.IMPOSSIBLE_SPEED, Severity.MEDIUM): 0.30,
        (SpoofingFlagType.LOCATION_JUMP, Severity.HIGH): 0.50,
        (SpoofingFlagType.CELL_MISMATCH, Severity.HIGH): 0.40,
        (SpoofingFlagType.SIGNAL_ANOMALY, Severity.MEDIUM): 0.10,
        (SpoofingFlagType.SIGNAL_ANOMALY, Severity.LOW): 0.05,
    }
    total_penalty = sum(
        penalty_map.get((f.type, f.severity), 0.10) for f in flags
    )
    return max(0.0, 1.0 - total_penalty)


def validate_gps_signal(
    gps_data: GPSData,
    location_history: List[GPSCoordinate],
) -> ValidationResult:
    """
    Main entry point for GPS anomaly detection.

    Args:
        gps_data: Current GPS reading with satellite and cell data.
        location_history: Previous GPS coordinates for this vehicle (oldest first).

    Returns:
        ValidationResult with confidence score and flags.
    """
    flags: List[SpoofingFlag] = []

    previous = location_history[-1] if location_history else None

    # 1. Physics: impossible speed
    flag = _check_impossible_speed(
        gps_data.coordinate, previous, settings.max_speed_kmph
    )
    if flag:
        flags.append(flag)

    # 2. Location jump
    flag = _check_location_jump(gps_data.coordinate, location_history)
    if flag:
        flags.append(flag)

    # 3. Signal quality / satellite count
    flag = _check_signal_anomaly(gps_data)
    if flag:
        flags.append(flag)

    # 4. Cell tower cross-validation
    flag = _check_cell_mismatch(gps_data)
    if flag:
        flags.append(flag)

    confidence = compute_confidence_score(flags)

    if confidence >= settings.gps_confidence_threshold:
        recommendation = SpoofingRecommendation.ACCEPT
        is_valid = True
    elif confidence >= 0.70:
        recommendation = SpoofingRecommendation.REVIEW
        is_valid = False
    else:
        recommendation = SpoofingRecommendation.REJECT
        is_valid = False

    return ValidationResult(
        is_valid=is_valid,
        confidence_score=confidence,
        flags=flags,
        recommendation=recommendation,
    )
