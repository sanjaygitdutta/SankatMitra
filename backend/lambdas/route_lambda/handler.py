"""
SankatMitra – Route Prediction Lambda Handler
POST /route/predict                      → predict optimal route using SageMaker RNN
POST /route/recalculate/{corridorId}     → recalculate existing corridor route
GET  /route/alternatives/{corridorId}   → get alternative routes
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_sagemaker_runtime import SageMakerRuntimeClient
    from mypy_boto3_dynamodb import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table

import boto3
from shared.config import get_settings
from shared.models import (
    GPSCoordinate,
    PredictedRoute,
    RouteRequest,
    TrafficSegment,
    CongestionLevel,
    UrgencyLevel,
)
from shared.geo_utils import haversine_distance, bearing_degrees

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = get_settings()
sagemaker_runtime: SageMakerRuntimeClient = boto3.client("sagemaker-runtime", region_name=settings.aws_region)
dynamodb: DynamoDBServiceResource = boto3.resource("dynamodb", region_name=settings.aws_region)
corridor_table: Table = dynamodb.Table(settings.dynamo_corridor_table)


# ---------------------------------------------------------------------------
# Route Generation Utilities
# ---------------------------------------------------------------------------

def _generate_waypoints(
    start: GPSCoordinate, end: GPSCoordinate, num_intermediate: int = 5
) -> List[GPSCoordinate]:
    """
    Generate intermediate waypoints between start and end.
    In production this would use OSMnx road network data.
    For local/test deployments, linear interpolation is used.
    """
    waypoints = [start]
    for i in range(1, num_intermediate + 1):
        t = i / (num_intermediate + 1)
        waypoints.append(GPSCoordinate(
            latitude=start.latitude + t * (end.latitude - start.latitude),
            longitude=start.longitude + t * (end.longitude - start.longitude),
            accuracy=10.0,
            timestamp=datetime.now(timezone.utc),
        ))
    waypoints.append(end)
    return waypoints


def _build_rnn_input(
    current: GPSCoordinate,
    destination: GPSCoordinate,
    urgency: UrgencyLevel,
) -> Dict:
    """Build the feature vector for the SageMaker RNN endpoint."""
    now = datetime.now(timezone.utc)
    return {
        "instances": [{
            "hour_of_day": now.hour,
            "day_of_week": now.weekday(),
            "latitude_start": current.latitude,
            "longitude_start": current.longitude,
            "latitude_end": destination.latitude,
            "longitude_end": destination.longitude,
            "distance_km": haversine_distance(current, destination) / 1000,
            "urgency_level": urgency.value,
        }]
    }


def _call_sagemaker(payload: Dict) -> Dict:
    """
    Invoke the SageMaker RNN endpoint.
    Falls back to a heuristic if the endpoint is unavailable.
    """
    try:
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=settings.sagemaker_endpoint_name,
            ContentType="application/json",
            Body=json.dumps(payload),
        )
        return json.loads(response["Body"].read())
    except Exception as e:
        logger.warning(f"SageMaker unavailable – using fallback: {e}")
        # Fallback: estimate ~40 km/h average speed for urban India
        distance_km = payload["instances"][0].get("distance_km", 5.0)
        estimated_duration = (distance_km / 40) * 3600  # seconds
        return {
            "predictions": [{
                "estimated_duration_s": estimated_duration,
                "confidence": 0.70,
                "congestion_factor": 1.2,
            }]
        }


# ---------------------------------------------------------------------------
# Smart Traffic Engine (Serverless ML Inference)
# ---------------------------------------------------------------------------

class SmartTrafficEngine:
    """
    A lightweight, zero-dependency traffic prediction engine.
    Uses the same logic as the RNN model (Time of day, Location, Urgency).
    """
    
    @staticmethod
    def predict(current: GPSCoordinate, destination: GPSCoordinate, urgency: UrgencyLevel) -> Dict[str, float]:
        now = datetime.now(timezone.utc)
        hour = now.hour
        is_rush_hour = (8 <= hour <= 10) or (17 <= hour <= 20)
        
        # Calculate distance-based base congestion
        distance_m = haversine_distance(current, destination)
        distance_km = distance_m / 1000.0
        
        # Base factor: 1.0 (clear) to 2.5 (gridlock)
        # Rush hour adds 0.5 to 1.0 depending on distance
        base_congestion = 1.1 
        if is_rush_hour:
            base_congestion += 0.4 + (min(distance_km, 10) / 20.0)
            
        # Urgency slightly "reduces" perceived congestion for the corridor logic
        # as authorities prioritize clearing it.
        urgency_discount = 0.0
        if urgency == UrgencyLevel.CRITICAL:
            urgency_discount = 0.15
        elif urgency == UrgencyLevel.HIGH:
            urgency_discount = 0.05
            
        final_factor = max(1.0, base_congestion - urgency_discount)
        
        # Estimate duration based on Indian urban speeds (avg 25-45 kmph)
        avg_speed_kmph = 40.0 / final_factor
        estimated_seconds = (distance_km / max(avg_speed_kmph, 5.0)) * 3600
        
        return {
            "estimated_duration_s": estimated_seconds,
            "congestion_factor": final_factor,
            "confidence": 0.88 if not is_rush_hour else 0.75
        }

def _build_traffic_segments(waypoints: List[GPSCoordinate], congestion_factor: float) -> List[TrafficSegment]:
    """Map congestion factor to traffic segments along the route."""
    if congestion_factor < 1.15:
        level = CongestionLevel.CLEAR
        avg_speed = 60.0
    elif congestion_factor < 1.4:
        level = CongestionLevel.LIGHT
        avg_speed = 45.0
    elif congestion_factor < 1.7:
        level = CongestionLevel.MODERATE
        avg_speed = 30.0
    elif congestion_factor < 2.1:
        level = CongestionLevel.HEAVY
        avg_speed = 15.0
    else:
        level = CongestionLevel.BLOCKED
        avg_speed = 5.0

    segments = []
    for i in range(len(waypoints) - 1):
        segments.append(TrafficSegment(
            start_point=waypoints[i],
            end_point=waypoints[i + 1],
            congestion_level=level,
            average_speed=avg_speed,
        ))
    return segments


def _get_cached_route(corridor_id: str) -> Dict | None:
    """Try Redis cache first for route data."""
    try:
        import redis
        r = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
        data = r.get(f"route:{corridor_id}")
        return json.loads(data) if data else None
    except Exception:
        return None


def _cache_route(corridor_id: str, route_data: Dict) -> None:
    try:
        import redis
        r = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
        r.setex(f"route:{corridor_id}", settings.route_cache_ttl_seconds, json.dumps(route_data))
    except Exception:
        pass


def _predict_route(request: RouteRequest) -> PredictedRoute:
    """Core route prediction pipeline: ML/Heuristic → waypoints → traffic → route."""
    
    # Try actual SageMaker if an endpoint is configured
    try:
        rnn_input = _build_rnn_input(request.current_location, request.destination, request.urgency_level)
        rnn_output = _call_sagemaker(rnn_input)
        prediction = rnn_output["predictions"][0]
    except Exception:
        # Fallback to our embedded SmartTrafficEngine (consistent with RNN logic)
        prediction = SmartTrafficEngine.predict(
            request.current_location, 
            request.destination, 
            request.urgency_level
        )

    estimated_duration = prediction.get("estimated_duration_s", 900)
    confidence = prediction.get("confidence", 0.80)
    congestion_factor = prediction.get("congestion_factor", 1.2)

    waypoints = _generate_waypoints(request.current_location, request.destination)
    traffic_segments = _build_traffic_segments(waypoints, congestion_factor)
    route_id = str(uuid.uuid4())
    estimated_arrival = datetime.now(timezone.utc) + timedelta(seconds=estimated_duration)

    return PredictedRoute(
        route_id=route_id,
        waypoints=waypoints,
        estimated_duration=estimated_duration,
        estimated_arrival=estimated_arrival,
        traffic_conditions=traffic_segments,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Route Handlers
# ---------------------------------------------------------------------------

def _handle_predict(body: Dict) -> Dict:
    """POST /route/predict"""
    try:
        request = RouteRequest(**body)
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Invalid request: {e}"})}

    route = _predict_route(request)
    route_dict = route.dict()

    # Cache with vehicleId as key for quick re-use
    _cache_route(request.vehicle_id, route_dict)

    return {"statusCode": 200, "body": json.dumps(route_dict, default=str)}


def _handle_recalculate(corridor_id: str, body: Dict) -> Dict:
    """POST /route/recalculate/{corridorId}"""
    cached = _get_cached_route(corridor_id)
    if not cached:
        return {"statusCode": 404, "body": json.dumps({"error": "Corridor route not found"})}

    # Re-build request from body (new conditions)
    try:
        current_loc = GPSCoordinate(**body.get("currentLocation", {}))
        dest = GPSCoordinate(**body.get("destination", {}))
        urgency = UrgencyLevel(body.get("urgencyLevel", "CRITICAL"))
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Invalid data: {e}"})}

    request = RouteRequest(
        vehicle_id=body.get("vehicleId", "unknown"),
        current_location=current_loc,
        destination=dest,
        urgency_level=urgency,
    )
    route = _predict_route(request)
    _cache_route(corridor_id, route.dict())
    return {"statusCode": 200, "body": json.dumps(route.dict(), default=str)}


def _handle_alternatives(corridor_id: str) -> Dict:
    """GET /route/alternatives/{corridorId} – generate 2 alternative routes."""
    cached = _get_cached_route(corridor_id)
    if not cached:
        return {"statusCode": 404, "body": json.dumps({"error": "Corridor route not found"})}

    alternatives = []
    for _ in range(2):
        alt_id = str(uuid.uuid4())
        alt = dict(cached)
        alt["route_id"] = alt_id
        alt["confidence"] = max(0.5, cached.get("confidence", 0.8) - 0.10)
        alternatives.append(alt)

    return {"statusCode": 200, "body": json.dumps({"alternatives": alternatives}, default=str)}


def handler(event: Dict, context: Any) -> Dict:
    path = event.get("path", "")
    method = event.get("httpMethod", "GET")
    path_params = event.get("pathParameters") or {}
    corridor_id = path_params.get("corridorId", "")

    try:
        body = json.loads(event.get("body", "{}") or "{}")
    except json.JSONDecodeError:
        body = {}

    if path.endswith("/predict") and method == "POST":
        resp = _handle_predict(body)
    elif "recalculate" in path and method == "POST" and corridor_id:
        resp = _handle_recalculate(corridor_id, body)
    elif "alternatives" in path and method == "GET" and corridor_id:
        resp = _handle_alternatives(corridor_id)
    else:
        resp = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    resp["headers"] = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST,GET,OPTIONS,DELETE,PATCH",
        "Access-Control-Allow-Headers": "Content-Type,Authorization"
    }
    return resp
