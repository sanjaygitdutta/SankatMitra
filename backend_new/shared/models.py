"""
SankatMitra – Data Models
Pydantic-free version (standard classes) for zero-dependency Lambdas.
"""
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
