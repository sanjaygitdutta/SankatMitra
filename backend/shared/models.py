"""
SankatMitra – Shared Data Models (Pydantic-free for Lambda compatibility)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional, Any


# ---------------------------------------------------------------------------
# Base Model Simulation
# ---------------------------------------------------------------------------

class BaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    
    def model_dump(self, by_alias=False, exclude_none=False):
        # Basic recursive dict conversion
        result = {}
        for k, v in self.__dict__.items():
            if v is None and exclude_none:
                continue
            if hasattr(v, 'model_dump'):
                result[k] = v.model_dump()
            elif isinstance(v, list):
                result[k] = [i.model_dump() if hasattr(i, 'model_dump') else i for i in v]
            elif isinstance(v, Enum):
                result[k] = v.value
            else:
                result[k] = v
        return result

    @classmethod
    def model_validate(cls, obj):
        if isinstance(obj, cls):
            return obj
        if isinstance(obj, dict):
            return cls(**obj)
        return obj

    def dict(self):
        return self.model_dump()


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
    LOCATION_JUMP = "LOCATION_JUMP"
    SIGNAL_ANOMALY = "SIGNAL_ANOMALY"
    CELL_MISMATCH = "CELL_MISMATCH"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SpoofingRecommendation(str, Enum):
    ACCEPT = "ACCEPT"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


# ---------------------------------------------------------------------------
# Core Models
# ---------------------------------------------------------------------------

class GPSCoordinate(BaseModel):
    def __init__(self, latitude=0.0, longitude=0.0, accuracy=10.0, timestamp=None, speed=None, heading=None, **kwargs):
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.accuracy = float(accuracy)
        self.timestamp = timestamp or datetime.utcnow().isoformat()
        self.speed = float(speed) if speed is not None else None
        self.heading = float(heading) if heading is not None else None
        super().__init__(**kwargs)


class Credentials(BaseModel):
    def __init__(self, vehicleId=None, registrationNumber=None, agencyId=None, digitalSignature=None, **kwargs):
        self.vehicle_id = vehicleId or kwargs.get("vehicle_id")
        self.registration_number = registrationNumber or kwargs.get("registration_number")
        self.agency_id = agencyId or kwargs.get("agency_id")
        self.digital_signature = digitalSignature or kwargs.get("digital_signature")
        super().__init__(**kwargs)


class AuthResult(BaseModel):
    def __init__(self, success=False, token=None, vehicle_type="AMBULANCE", expires_at=None, error_code=None, **kwargs):
        self.success = success
        self.token = token
        self.vehicle_type = vehicle_type
        self.expires_at = expires_at
        self.error_code = error_code
        super().__init__(**kwargs)


class TokenValidation(BaseModel):
    def __init__(self, valid=False, vehicle_id=None, expires_at=None, error=None, **kwargs):
        self.valid = valid
        self.vehicle_id = vehicle_id
        self.expires_at = expires_at
        self.error = error
        super().__init__(**kwargs)


class RouteRequest(BaseModel):
    def __init__(self, vehicle_id=None, current_location=None, destination=None, urgency_level="MEDIUM", **kwargs):
        self.vehicle_id = vehicle_id
        self.current_location = GPSCoordinate.model_validate(current_location) if current_location else None
        self.destination = GPSCoordinate.model_validate(destination) if destination else None
        self.urgency_level = UrgencyLevel(urgency_level) if isinstance(urgency_level, str) else urgency_level
        super().__init__(**kwargs)


class TrafficSegment(BaseModel):
    def __init__(self, start_point=None, end_point=None, congestion_level="CLEAR", average_speed=40.0, **kwargs):
        self.start_point = GPSCoordinate.model_validate(start_point) if start_point else None
        self.end_point = GPSCoordinate.model_validate(end_point) if end_point else None
        self.congestion_level = CongestionLevel(congestion_level) if isinstance(congestion_level, str) else congestion_level
        self.average_speed = average_speed
        super().__init__(**kwargs)


class PredictedRoute(BaseModel):
    def __init__(self, route_id=None, waypoints=None, estimated_duration=0, congestion_level="CLEAR", estimated_arrival=None, traffic_conditions=None, confidence=0.8, **kwargs):
        self.route_id = route_id
        self.waypoints = [GPSCoordinate.model_validate(w) for w in (waypoints or [])]
        self.estimated_duration = estimated_duration
        self.congestion_level = CongestionLevel(congestion_level) if isinstance(congestion_level, str) else congestion_level
        self.estimated_arrival = estimated_arrival
        self.traffic_conditions = [TrafficSegment.model_validate(s) for s in (traffic_conditions or [])]
        self.confidence = confidence
        super().__init__(**kwargs)


class CorridorRequest(BaseModel):
    def __init__(self, vehicle_id=None, currentLocation=None, destination=None, urgencyLevel="MEDIUM", missionType="EMERGENCY", **kwargs):
        self.vehicle_id = vehicle_id
        self.current_location = GPSCoordinate.model_validate(currentLocation or kwargs.get("current_location"))
        self.destination = GPSCoordinate.model_validate(destination)
        self.urgency_level = UrgencyLevel(urgencyLevel or kwargs.get("urgencyLevel", "MEDIUM"))
        self.mission_type = missionType
        super().__init__(**kwargs)


class Corridor(BaseModel):
    def __init__(self, corridorId=None, emergencyVehicleId=None, status="REQUESTED", route=None, **kwargs):
        self.corridor_id = corridorId or kwargs.get("corridorId")
        self.emergency_vehicle_id = emergencyVehicleId or kwargs.get("emergencyVehicleId")
        self.status = CorridorStatus(status) if isinstance(status, str) else status
        self.route = [GPSCoordinate.model_validate(w) for w in (route or [])]
        self.destination = GPSCoordinate.model_validate(kwargs.get("destination")) if kwargs.get("destination") else None
        super().__init__(**kwargs)


class GPSData(BaseModel):
    def __init__(self, coordinate=None, satellite_count=8, signal_strength=-80.0, cell_tower_data=None, **kwargs):
        self.coordinate = GPSCoordinate.model_validate(coordinate) if coordinate else None
        self.satellite_count = satellite_count
        self.signal_strength = signal_strength
        self.cell_tower_data = cell_tower_data
        super().__init__(**kwargs)


class SpoofingFlag(BaseModel):
    def __init__(self, type=None, severity="LOW", details="", **kwargs):
        self.type = SpoofingFlagType(type) if isinstance(type, str) else type
        self.severity = Severity(severity) if isinstance(severity, str) else severity
        self.details = details
        super().__init__(**kwargs)


class ValidationResult(BaseModel):
    def __init__(self, is_valid=True, confidence_score=1.0, flags=None, recommendation="ACCEPT", **kwargs):
        self.is_valid = is_valid
        self.confidence_score = confidence_score
        self.flags = [SpoofingFlag.model_validate(f) for f in (flags or [])]
        self.recommendation = SpoofingRecommendation(recommendation) if isinstance(recommendation, str) else recommendation
        super().__init__(**kwargs)


class AlertLog(BaseModel):
    def __init__(self, alert_id=None, corridor_id=None, recipient_vehicle_id=None, sent_at=None, delivery_status="SENT", **kwargs):
        self.alert_id = alert_id
        self.corridor_id = corridor_id
        self.recipient_vehicle_id = recipient_vehicle_id
        self.sent_at = sent_at or datetime.utcnow().isoformat()
        self.delivery_status = DeliveryStatus(delivery_status) if isinstance(delivery_status, str) else delivery_status
        super().__init__(**kwargs)


class AlertResult(BaseModel):
    def __init__(self, total_sent=0, successful=0, failed=0, delivery_time_ms=0.0, **kwargs):
        self.total_sent = total_sent
        self.successful = successful
        self.failed = failed
        self.delivery_time_ms = delivery_time_ms
        super().__init__(**kwargs)

# Additional stubs / less critical models
class CellTowerInfo(BaseModel): pass
class VehicleLocation(BaseModel): pass
class TrafficEvent(BaseModel): pass
class CorridorUpdate(BaseModel): pass
class Alert(BaseModel): pass
class SpoofingEvidence(BaseModel): pass
class MissionRecord(BaseModel): pass
class VehicleRegistration(BaseModel):
    def __init__(self, vehicle_id=None, registration_number=None, vehicle_type="AMBULANCE", agency_id=None, agency_name=None, **kwargs):
        self.vehicle_id = vehicle_id
        self.registration_number = registration_number
        self.vehicle_type = vehicle_type
        self.agency_id = agency_id
        self.agency_name = agency_name
        super().__init__(**kwargs)
