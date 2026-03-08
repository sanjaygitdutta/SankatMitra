"""
SankatMitra – Corridor Management Lambda Handler
POST   /corridor/activate     → activate a new emergency corridor (full orchestration)
GET    /corridor/{id}         → get corridor state
PATCH  /corridor/{id}         → update corridor (route change / urgency)
DELETE /corridor/{id}         → deactivate corridor
GET    /corridors             → list all active corridors
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table
    from mypy_boto3_lambda import LambdaClient

import boto3
from botocore.exceptions import ClientError

from shared.config import get_settings
from shared.models import (
    Corridor,
    CorridorRequest,
    CorridorStatus,
    CorridorUpdate,
    GPSCoordinate,
    UrgencyLevel,
)
from shared.security import token_from_header, verify_token

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = get_settings()
dynamodb: DynamoDBServiceResource = boto3.resource("dynamodb", region_name=settings.aws_region)
corridor_table: Table = dynamodb.Table(settings.dynamo_corridor_table)
lambda_client: LambdaClient = boto3.client("lambda", region_name=settings.aws_region)


# ---------------------------------------------------------------------------
# State Machine helpers
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    CorridorStatus.REQUESTED: [CorridorStatus.AUTHENTICATED],
    CorridorStatus.AUTHENTICATED: [CorridorStatus.ROUTE_CALCULATED],
    CorridorStatus.ROUTE_CALCULATED: [CorridorStatus.ACTIVE],
    CorridorStatus.ACTIVE: [CorridorStatus.PAUSED, CorridorStatus.COMPLETED],
    CorridorStatus.PAUSED: [CorridorStatus.ACTIVE, CorridorStatus.COMPLETED],
    CorridorStatus.COMPLETED: [],
}


def _can_transition(current: CorridorStatus, target: CorridorStatus) -> bool:
    return target in VALID_TRANSITIONS.get(current, [])


def _to_dynamo(obj: Dict) -> Dict:
    """Convert Python types to DynamoDB-compatible types."""
    result = {}
    for k, v in obj.items():
        if isinstance(v, float):
            result[k] = Decimal(str(v))
        elif isinstance(v, dict):
            result[k] = _to_dynamo(v)
        elif isinstance(v, list):
            result[k] = [_to_dynamo(i) if isinstance(i, dict) else i for i in v]
        elif v is None:
            pass  # Skip nulls
        else:
            result[k] = str(v) if not isinstance(v, (str, int, bool, Decimal)) else v
    return result


# ---------------------------------------------------------------------------
# Service Invocation Helpers
# ---------------------------------------------------------------------------

def _invoke_lambda(function_name: str, payload: Dict) -> Dict:
    """Synchronously invoke another Lambda function."""
    try:
        resp = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        body = json.loads(resp["Payload"].read())
        return json.loads(body.get("body", "{}"))
    except Exception as e:
        logger.error(f"Lambda invoke error ({function_name}): {e}")
        raise


# ---------------------------------------------------------------------------
# Corridor CRUD Operations
# ---------------------------------------------------------------------------

def _save_corridor(corridor_id: str, data: Dict) -> None:
    try:
        corridor_table.put_item(Item=_to_dynamo({**data, "corridorId": corridor_id}))
    except ClientError as e:
        logger.error(f"DynamoDB put error: {e}")
        raise


def _get_corridor(corridor_id: str) -> Optional[Dict]:
    try:
        resp = corridor_table.get_item(Key={"corridorId": corridor_id})
        return resp.get("Item")
    except ClientError as e:
        logger.error(f"DynamoDB get error: {e}")
        return None


# ---------------------------------------------------------------------------
# Route Handlers
# ---------------------------------------------------------------------------

def _handle_activate(body: Dict, vehicle_id: str) -> Dict:
    """
    POST /corridor/activate
    Full orchestration: Auth check → Route Prediction → Alert → ACTIVE
    """
    try:
        req = CorridorRequest(**{**body, "vehicle_id": vehicle_id})
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Invalid request: {e}"})}

    corridor_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Create corridor record in REQUESTED state
    corridor_data = {
        "corridorId": corridor_id,
        "emergencyVehicleId": vehicle_id,
        "status": CorridorStatus.REQUESTED.value,
        "urgencyLevel": req.urgency_level.value,
        "missionType": req.mission_type,
        "destinationLat": req.destination.latitude,
        "destinationLon": req.destination.longitude,
        "alertRadius": settings.alert_radius_meters,
        "createdAt": now.isoformat(),
        "updatedAt": now.isoformat(),
        "lastMovementAt": now.isoformat(),
    }
    _save_corridor(corridor_id, corridor_data)

    # Transition: REQUESTED → AUTHENTICATED (vehicle already authenticated via API GW authorizer)
    corridor_data["status"] = CorridorStatus.AUTHENTICATED.value
    corridor_data["updatedAt"] = datetime.now(timezone.utc).isoformat()

    # Invoke route prediction Lambda
    route_result = {}
    try:
        route_result = _invoke_lambda("sankatmitra-route-lambda", {
            "path": "/route/predict",
            "httpMethod": "POST",
            "body": json.dumps({
                "vehicle_id": vehicle_id,
                "currentLocation": body.get("currentLocation", {}),
                "destination": {"latitude": req.destination.latitude, "longitude": req.destination.longitude},
                "urgencyLevel": req.urgency_level.value,
            }),
        })
    except Exception as e:
        logger.error(f"Route prediction failed: {e}")
        # Fallback will be handled below if route_result is empty
    
    # Fallback: If no route from ML service, generate direct waypoints
    route_waypoints = route_result.get("waypoints", [])
    if not route_waypoints:
        from shared.geo_utils import haversine_distance
        dist = haversine_distance(
            GPSCoordinate.model_validate(body.get("currentLocation", {})),
            req.destination
        )
        # Simple 2-point fallback route
        route_waypoints = [
            body.get("currentLocation", {}),
            {"latitude": req.destination.latitude, "longitude": req.destination.longitude}
        ]
        route_result["estimated_duration"] = int((dist / 10) + 60) # ~36km/h avg
        logger.info(f"Using fallback linear route for corridor {corridor_id}")

    corridor_data["routeId"] = route_result.get("route_id", f"fb-{corridor_id}")
    corridor_data["estimatedDuration"] = route_result.get("estimated_duration")
    corridor_data["status"] = CorridorStatus.ROUTE_CALCULATED.value
    corridor_data["updatedAt"] = datetime.now(timezone.utc).isoformat()

    # Transition: ROUTE_CALCULATED → ACTIVE
    corridor_data["status"] = CorridorStatus.ACTIVE.value
    corridor_data["activatedAt"] = datetime.now(timezone.utc).isoformat()
    corridor_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    
    # Include route waypoints in the saved data and response
    corridor_data["route"] = route_waypoints
    
    _save_corridor(corridor_id, corridor_data)

    # Trigger alert distribution asynchronously
    try:
        lambda_client.invoke(
            FunctionName="sankatmitra-alert-lambda",
            InvocationType="Event",  # Async – fire and forget
            Payload=json.dumps({
                "path": "/alert/send",
                "httpMethod": "POST",
                "body": json.dumps({
                    "corridorId": corridor_id,
                    "routeWaypoints": route_waypoints,
                    "etaSeconds": route_result.get("estimated_duration", 300),
                    "ambulanceLocation": body.get("currentLocation", {}),
                }),
            }),
        )
    except Exception as e:
        logger.warning(f"Alert dispatch failed (non-fatal): {e}")

    # Audit log
    logger.info(json.dumps({
        "event": "corridor_activated",
        "corridorId": corridor_id,
        "vehicleId": vehicle_id,
        "urgencyLevel": req.urgency_level.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    # Return full data expected by frontend (Corridor model in Flutter)
    return {
        "statusCode": 201,
        "body": json.dumps({
            "corridorId": corridor_id,
            "vehicleId": vehicle_id,
            "status": CorridorStatus.ACTIVE.value,
            "urgencyLevel": req.urgency_level.value,
            "missionType": req.mission_type,
            "route": route_waypoints,
            "destination": {
                "latitude": req.destination.latitude,
                "longitude": req.destination.longitude
            },
            "startTime": corridor_data["activatedAt"],
            "estimatedDuration": corridor_data.get("estimatedDuration"),
        }),
    }


def _handle_get(corridor_id: str) -> Dict:
    item = _get_corridor(corridor_id)
    if not item:
        return {"statusCode": 404, "body": json.dumps({"error": "Corridor not found"})}
    return {"statusCode": 200, "body": json.dumps(dict(item), default=str)}


def _handle_update(corridor_id: str, body: Dict) -> Dict:
    item = _get_corridor(corridor_id)
    if not item:
        return {"statusCode": 404, "body": json.dumps({"error": "Corridor not found"})}

    updates = {}
    if "urgencyLevel" in body:
        updates["urgencyLevel"] = body["urgencyLevel"]
    if "status" in body:
        current_status = CorridorStatus(item.get("status", CorridorStatus.ACTIVE.value))
        new_status = CorridorStatus(body["status"])
        if not _can_transition(current_status, new_status):
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Invalid transition {current_status} → {new_status}"}),
            }
        updates["status"] = new_status.value
    updates["updatedAt"] = datetime.now(timezone.utc).isoformat()

    update_expr = "SET " + ", ".join(f"#{k} = :{k}" for k in updates)
    attr_names = {f"#{k}": k for k in updates}
    attr_values = {f":{k}": str(v) if not isinstance(v, (int, float)) else v for k, v in updates.items()}

    corridor_table.update_item(
        Key={"corridorId": corridor_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )
    return {"statusCode": 200, "body": json.dumps({"corridorId": corridor_id, "updated": list(updates.keys())})}


def _handle_deactivate(corridor_id: str) -> Dict:
    item = _get_corridor(corridor_id)
    if not item:
        return {"statusCode": 404, "body": json.dumps({"error": "Corridor not found"})}

    corridor_table.update_item(
        Key={"corridorId": corridor_id},
        UpdateExpression="SET #s = :completed, updatedAt = :ts",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":completed": CorridorStatus.COMPLETED.value,
            ":ts": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Send clearance alerts
    try:
        lambda_client.invoke(
            FunctionName="sankatmitra-alert-lambda",
            InvocationType="Event",
            Payload=json.dumps({
                "path": f"/alert/cancel/{corridor_id}",
                "httpMethod": "DELETE",
                "pathParameters": {"corridorId": corridor_id},
                "body": "{}",
            }),
        )
    except Exception:
        pass

    logger.info(json.dumps({
        "event": "corridor_deactivated",
        "corridorId": corridor_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))
    return {"statusCode": 200, "body": json.dumps({"deactivated": True, "corridorId": corridor_id})}


def _handle_list() -> Dict:
    try:
        resp = corridor_table.scan(
            FilterExpression="#s = :active",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":active": CorridorStatus.ACTIVE.value},
        )
        items = resp.get("Items", [])
        return {"statusCode": 200, "body": json.dumps({"corridors": items, "count": len(items)}, default=str)}
    except ClientError as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


# ---------------------------------------------------------------------------
# Lambda Entry Point
# ---------------------------------------------------------------------------

def handler(event: Dict, context: Any) -> Dict:
    try:
        return _internal_handler(event, context)
    except Exception as e:
        import traceback
        logger.error(f"FATAL HANDLER ERROR: {e}\n{traceback.format_exc()}")
        return {
            "statusCode": 500, 
            "body": json.dumps({"error": "Internal server error", "details": str(e)}),
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        }

def _internal_handler(event: Dict, context: Any) -> Dict:
    path = event.get("path", "")
    method = event.get("httpMethod", "GET")
    path_params = event.get("pathParameters") or {}
    corridor_id = path_params.get("id", "")

    # Extract vehicle_id from JWT (set by API GW authorizer)
    auth_header = (event.get("headers") or {}).get("Authorization", "")
    token = token_from_header(auth_header)
    vehicle_id = "unknown"
    if token:
        try:
            payload = verify_token(token)
            vehicle_id = payload.get("sub", "unknown")
        except Exception:
            return {"statusCode": 401, "body": json.dumps({"error": "Invalid token"})}

    try:
        body = json.loads(event.get("body", "{}") or "{}")
    except json.JSONDecodeError:
        body = {}

    if path.endswith("/activate") and method == "POST":
        resp = _handle_activate(body, vehicle_id)
    elif path.endswith("/corridors") and method == "GET":
        resp = _handle_list()
    elif corridor_id and method == "GET":
        resp = _handle_get(corridor_id)
    elif corridor_id and method in ("PATCH", "PUT"):
        resp = _handle_update(corridor_id, body)
    elif corridor_id and method == "DELETE":
        resp = _handle_deactivate(corridor_id)
    else:
        resp = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    resp["headers"] = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST,GET,OPTIONS,DELETE,PATCH",
        "Access-Control-Allow-Headers": "Content-Type,Authorization"
    }
    return resp
