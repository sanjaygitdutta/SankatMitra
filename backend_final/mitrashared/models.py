"""
SankatMitra – Data Models
Pydantic-free version (standard classes) for zero-dependency Lambdas.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Any

class VehicleType(Enum):
    AMBULANCE = "AMBULANCE"
    CIVILIAN = "CIVILIAN"
    POLICE = "POLICE"

class SignalQuality(Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    POOR = "POOR"
    NONE = "NONE"

class AlertDirection(Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    PULL_OVER = "PULL_OVER"

class UrgencyLevel(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"

class CorridorStatus(Enum):
    REQUESTED = "REQUESTED"
    AUTHENTICATED = "AUTHENTICATED"
    ROUTE_CALCULATED = "ROUTE_CALCULATED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"

class CongestionLevel(Enum):
    CLEAR = "CLEAR"
    LIGHT = "LIGHT"
    MODERATE = "MODERATE"
    HEAVY = "HEAVY"
    BLOCKED = "BLOCKED"

@dataclass
class GPSCoordinate:
    latitude: float
    longitude: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    accuracy: float = 0.0
    speed: float = 0.0
    heading: float = 0.0

    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> 'GPSCoordinate':
        ts = data.get('timestamp')
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return cls(
            latitude=float(data['latitude']),
            longitude=float(data['longitude']),
            timestamp=ts or datetime.utcnow(),
            accuracy=float(data.get('accuracy', 0.0)),
            speed=float(data.get('speed', 0.0)),
            heading=float(data.get('heading', 0.0)),
        )

    def dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timestamp": self.timestamp.isoformat(),
            "accuracy": self.accuracy,
            "speed": self.speed,
            "heading": self.heading,
        }

@dataclass
class CorridorRequest:
    destination: GPSCoordinate
    urgency_level: UrgencyLevel
    vehicle_id: str
    mission_type: str = "EMERGENCY"

    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> 'CorridorRequest':
        return cls(
            destination=GPSCoordinate.model_validate(data.get('destination', {})),
            urgency_level=UrgencyLevel(data.get('urgencyLevel', data.get('urgency_level', 'HIGH'))),
            vehicle_id=data.get('vehicle_id', data.get('vehicleId', 'unknown')),
            mission_type=data.get('missionType', data.get('mission_type', 'EMERGENCY'))
        )

@dataclass
class CorridorUpdate:
    status: Optional[CorridorStatus] = None
    urgency_level: Optional[UrgencyLevel] = None

@dataclass
class RouteRequest:
    current_location: GPSCoordinate
    destination: GPSCoordinate
    urgency_level: UrgencyLevel
    vehicle_id: str

    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> 'RouteRequest':
        return cls(
            current_location=GPSCoordinate.model_validate(data.get('currentLocation', data.get('current_location', {}))),
            destination=GPSCoordinate.model_validate(data.get('destination', {})),
            urgency_level=UrgencyLevel(data.get('urgencyLevel', data.get('urgency_level', 'HIGH'))),
            vehicle_id=data.get('vehicle_id', data.get('vehicleId', 'unknown'))
        )

@dataclass
class TrafficSegment:
    start_point: GPSCoordinate
    end_point: GPSCoordinate
    congestion_level: CongestionLevel
    average_speed: float

    def dict(self) -> Dict[str, Any]:
        return {
            "start_point": self.start_point.dict(),
            "end_point": self.end_point.dict(),
            "congestion_level": self.congestion_level.value,
            "average_speed": self.average_speed,
        }

@dataclass
class PredictedRoute:
    route_id: str
    waypoints: List[GPSCoordinate]
    estimated_duration: int
    estimated_arrival: datetime
    traffic_conditions: List[TrafficSegment]
    confidence: float

    def dict(self) -> Dict[str, Any]:
        return {
            "route_id": self.route_id,
            "waypoints": [w.dict() for w in self.waypoints],
            "estimated_duration": self.estimated_duration,
            "estimated_arrival": self.estimated_arrival.isoformat() if isinstance(self.estimated_arrival, datetime) else self.estimated_arrival,
            "traffic_conditions": [s.dict() for s in self.traffic_conditions],
            "confidence": self.confidence,
        }


@dataclass
class GPSData:
    vehicleId: str
    coordinate: GPSCoordinate
    satellite_count: int = 0
    signal_strength: float = 0.0
    cell_tower_data: List[Any] = field(default_factory=list)

class SpoofingFlagType(Enum):
    IMPOSSIBLE_SPEED = "IMPOSSIBLE_SPEED"
    LOCATION_JUMP = "LOCATION_JUMP"
    SIGNAL_ANOMALY = "SIGNAL_ANOMALY"
    CELL_MISMATCH = "CELL_MISMATCH"

class Severity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

@dataclass
class SpoofingFlag:
    type: SpoofingFlagType
    severity: Severity
    details: str

    def dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "details": self.details,
        }

class SpoofingRecommendation(Enum):
    ACCEPT = "ACCEPT"
    REVIEW = "REVIEW"
    REJECT = "REJECT"

@dataclass
class ValidationResult:
    is_valid: bool
    confidence_score: float
    flags: List[SpoofingFlag]
    recommendation: SpoofingRecommendation

@dataclass
class VehicleLocation:
    vehicleId: str
    vehicleType: VehicleType
    coordinate: GPSCoordinate
    fcmToken: Optional[str] = None
    isActive: bool = True

@dataclass
class Corridor:
    corridorId: str
    ambulanceId: str
    routeWaypoints: List[GPSCoordinate]
    startTime: datetime
    urgency: UrgencyLevel = UrgencyLevel.HIGH
    status: str = "ACTIVE"

@dataclass
class Alert:
    alertId: str
    corridorId: str
    targetVehicleId: str
    direction: AlertDirection
    etaSeconds: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
@dataclass
class Credentials:
    vehicle_id: str
    password: Optional[str] = None
    registration_number: Optional[str] = None
    agency_id: Optional[str] = None
    digital_signature: Optional[str] = None

    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> 'Credentials':
        return cls(
            vehicle_id=data.get('vehicleId', data.get('vehicle_id')),
            password=data.get('password'),
            registration_number=data.get('registrationNumber'),
            agency_id=data.get('agencyId'),
            digital_signature=data.get('digitalSignature', data.get('signature', data.get('digital_signature')))
        )

@dataclass
class AuthResult:
    success: bool
    token: Optional[str] = None
    vehicle_type: str = "AMBULANCE"
    expires_at: Optional[datetime] = None

@dataclass
class TokenValidation:
    valid: bool
    vehicle_id: Optional[str] = None
    error: Optional[str] = None
