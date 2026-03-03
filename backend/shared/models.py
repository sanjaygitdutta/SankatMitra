"""
SankatMitra – Shared Pydantic Data Models
Used across all Lambda functions.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SignalQuality(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CongestionLevel(str, Enum):
    CLEAR = "CLEAR"
    LIGHT = "LIGHT"
    MODERATE = "MODERATE"
    HEAVY = "HEAVY"
    BLOCKED = "BLOCKED"


class UrgencyLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


class CorridorStatus(str, Enum):
    REQUESTED = "REQUESTED"
    AUTHENTICATED = "AUTHENTICATED"
    ROUTE_CALCULATED = "ROUTE_CALCULATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class VehicleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class AlertDirection(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    PULL_OVER = "PULL_OVER"


class DeliveryStatus(str, Enum):
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"


class SpoofingFlagType(str, Enum):
    IMPOSSIBLE_SPEED = "IMPOSSIBLE_SPEED"
    SIGNAL_ANOMALY = "SIGNAL_ANOMALY"
    LOCATION_JUMP = "LOCATION_JUMP"
    CELL_MISMATCH = "CELL_MISMATCH"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class SpoofingRecommendation(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REVIEW = "REVIEW"


class MissionStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class TrafficEventType(str, Enum):
    ACCIDENT = "ACCIDENT"
    CONSTRUCTION = "CONSTRUCTION"
    EVENT = "EVENT"
    CLOSURE = "CLOSURE"


# ---------------------------------------------------------------------------
# Core Geographic Models
# ---------------------------------------------------------------------------

class GPSCoordinate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in degrees")
    accuracy: float = Field(default=10.0, ge=0, description="Accuracy in metres")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    speed: Optional[float] = Field(default=None, ge=0, description="Speed in m/s")
    heading: Optional[float] = Field(default=None, ge=0, lt=360, description="Heading in degrees")


class CellTowerInfo(BaseModel):
    tower_id: str
    latitude: float
    longitude: float
    signal_strength: float  # dBm


class GPSData(BaseModel):
    coordinate: GPSCoordinate
    satellite_count: int = Field(ge=0)
    signal_strength: float
    cell_tower_data: Optional[List[CellTowerInfo]] = None


class VehicleLocation(BaseModel):
    vehicle_id: str
    coordinate: GPSCoordinate
    signal_quality: SignalQuality
    last_update: datetime


# ---------------------------------------------------------------------------
# Authentication Models
# ---------------------------------------------------------------------------

class Credentials(BaseModel):
    vehicle_id: str
    registration_number: str
    agency_id: str
    digital_signature: str


class AuthResult(BaseModel):
    success: bool
    token: Optional[str] = None
    vehicle_type: str = "AMBULANCE"
    expires_at: Optional[datetime] = None
    error_code: Optional[str] = None


class TokenValidation(BaseModel):
    valid: bool
    vehicle_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    error: Optional[str] = None


class VehicleRegistration(BaseModel):
    vehicle_id: str
    registration_number: str
    vehicle_type: str = "AMBULANCE"
    agency_id: str
    agency_name: str
    state: str
    district: str
    registered_at: datetime
    status: VehicleStatus
    last_authentication: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Traffic & Route Models
# ---------------------------------------------------------------------------

class TrafficSegment(BaseModel):
    start_point: GPSCoordinate
    end_point: GPSCoordinate
    congestion_level: CongestionLevel
    average_speed: float  # km/h


class TrafficEvent(BaseModel):
    event_type: TrafficEventType
    location: GPSCoordinate
    impact: Severity
    start_time: datetime
    end_time: Optional[datetime] = None


class RouteRequest(BaseModel):
    vehicle_id: str
    current_location: GPSCoordinate
    destination: GPSCoordinate
    vehicle_type: str = "AMBULANCE"
    urgency_level: UrgencyLevel = UrgencyLevel.CRITICAL


class PredictedRoute(BaseModel):
    route_id: str
    waypoints: List[GPSCoordinate]
    estimated_duration: float  # seconds
    estimated_arrival: datetime
    traffic_conditions: List[TrafficSegment] = []
    confidence: float = Field(ge=0, le=1)


# ---------------------------------------------------------------------------
# Corridor Models
# ---------------------------------------------------------------------------

class CorridorRequest(BaseModel):
    vehicle_id: str
    destination: GPSCoordinate
    urgency_level: UrgencyLevel = UrgencyLevel.CRITICAL
    mission_type: str = "EMERGENCY"


class CorridorUpdate(BaseModel):
    new_route: Optional[PredictedRoute] = None
    urgency_level: Optional[UrgencyLevel] = None
    status: Optional[CorridorStatus] = None


class Corridor(BaseModel):
    corridor_id: str
    emergency_vehicle_id: str
    route: PredictedRoute
    alert_radius: float = 500.0  # metres
    status: CorridorStatus = CorridorStatus.REQUESTED
    created_at: datetime
    updated_at: datetime
    last_movement_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Alert Models
# ---------------------------------------------------------------------------

class Alert(BaseModel):
    alert_id: str
    vehicle_id: str
    emergency_vehicle_type: str = "AMBULANCE"
    direction: AlertDirection
    estimated_arrival: float  # seconds
    route_visualization: Optional[str] = None  # GeoJSON string
    corridor_id: str


class AlertResult(BaseModel):
    total_sent: int
    successful: int
    failed: int
    delivery_time_ms: float


class AlertLog(BaseModel):
    alert_id: str
    corridor_id: str
    recipient_vehicle_id: str
    sent_at: datetime
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    delivery_status: DeliveryStatus = DeliveryStatus.SENT
    failure_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Spoofing Models
# ---------------------------------------------------------------------------

class SpoofingFlag(BaseModel):
    type: SpoofingFlagType
    severity: Severity
    details: str


class ValidationResult(BaseModel):
    is_valid: bool
    confidence_score: float = Field(ge=0, le=1)
    flags: List[SpoofingFlag] = []
    recommendation: SpoofingRecommendation


class SpoofingEvidence(BaseModel):
    vehicle_id: str
    gps_data: GPSData
    flags: List[SpoofingFlag]
    confidence_score: float
    detected_at: datetime


# ---------------------------------------------------------------------------
# Mission Record
# ---------------------------------------------------------------------------

class MissionRecord(BaseModel):
    mission_id: str
    vehicle_id: str
    corridor_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    start_location: GPSCoordinate
    destination: GPSCoordinate
    actual_route: List[GPSCoordinate] = []
    distance_traveled: float = 0.0  # km
    average_speed: float = 0.0  # km/h
    alerts_sent: int = 0
    status: MissionStatus = MissionStatus.IN_PROGRESS
