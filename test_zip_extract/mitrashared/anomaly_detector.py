"""
SankatMitra – GPS Anomaly Detection Algorithm
Physics-based + multi-factor validation for GPS signals.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import List, Optional

from .config import get_settings
from .geo_utils import calculate_speed_kmph, haversine_distance
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
    if not history:
        return None
    last = history[-1]
    dist = haversine_distance(last, current)
    dt = abs((current.timestamp - last.timestamp).total_seconds())
    max_legal_dist = 41.7 * dt + 50  # ~150 km/h + 50m buffer
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
    if gps_data.signal_strength < -130:
        return SpoofingFlag(
            type=SpoofingFlagType.SIGNAL_ANOMALY,
            severity=Severity.LOW,
            details=f"Weak signal: {gps_data.signal_strength:.1f} dBm",
        )
    return None


def calculate_acceleration_ms2(p1, p2, p3):
    # This is a stub to prevent import errors in case anyone still calls it
    return 0.0

def compute_confidence_score(flags: List[SpoofingFlag]) -> float:
    penalty_map = {
        (SpoofingFlagType.IMPOSSIBLE_SPEED, Severity.HIGH): 0.60,
        (SpoofingFlagType.IMPOSSIBLE_SPEED, Severity.MEDIUM): 0.30,
        (SpoofingFlagType.LOCATION_JUMP, Severity.HIGH): 0.50,
        (SpoofingFlagType.SIGNAL_ANOMALY, Severity.MEDIUM): 0.10,
        (SpoofingFlagType.SIGNAL_ANOMALY, Severity.LOW): 0.05,
    }
    total_penalty = sum(penalty_map.get((f.type, f.severity), 0.10) for f in flags)
    return max(0.0, 1.0 - total_penalty)


def validate_gps_signal(
    gps_data: GPSData,
    location_history: List[GPSCoordinate],
) -> ValidationResult:
    flags: List[SpoofingFlag] = []
    previous = location_history[-1] if location_history else None

    # Physics & Logic Checks
    flag = _check_impossible_speed(gps_data.coordinate, previous, settings.max_speed_kmph)
    if flag: flags.append(flag)

    flag = _check_location_jump(gps_data.coordinate, location_history)
    if flag: flags.append(flag)

    flag = _check_signal_anomaly(gps_data)
    if flag: flags.append(flag)

    confidence = compute_confidence_score(flags)
    is_valid = confidence >= settings.gps_confidence_threshold
    
    recommendation = (
        SpoofingRecommendation.ACCEPT if is_valid else
        SpoofingRecommendation.REVIEW if confidence >= 0.70 else
        SpoofingRecommendation.REJECT
    )

    return ValidationResult(
        is_valid=is_valid,
        confidence_score=confidence,
        flags=flags,
        recommendation=recommendation,
    )
