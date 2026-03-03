"""
SankatMitra – Alert Distribution Lambda Handler
POST   /alert/send              → send push notifications to civilian vehicles in corridor radius
PATCH  /alert/update/{corridorId} → update alerts when route changes
DELETE /alert/cancel/{corridorId} → cancel corridor alerts (clearance confirmed)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table
    from mypy_boto3_sns import SNSClient

import boto3
import requests
from botocore.exceptions import ClientError

from backend.shared.config import get_settings
from backend.shared.models import Alert, AlertDirection, AlertLog, AlertResult, DeliveryStatus, GPSCoordinate
from backend.shared.geo_utils import is_within_corridor, haversine_distance, bearing_degrees
from backend.shared.bedrock_service import get_bedrock_service

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = get_settings()
dynamodb: DynamoDBServiceResource = boto3.resource("dynamodb", region_name=settings.aws_region)
alert_table: Table = dynamodb.Table(settings.dynamo_alert_table)
location_table: Table = dynamodb.Table(settings.dynamo_location_table)
sns: SNSClient = boto3.client("sns", region_name=settings.aws_region)


# ---------------------------------------------------------------------------
# FCM Push Notification Helper (Firebase)
# ---------------------------------------------------------------------------

FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send"
_MAX_BATCH_SIZE = 1000
_MAX_RETRIES = 3


def _send_fcm(registration_tokens: List[str], notification: Dict) -> Dict:
    """Send FCM push notification to a batch of devices."""
    headers = {
        "Authorization": f"key={settings.firebase_server_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "registration_ids": registration_tokens[:_MAX_BATCH_SIZE],
        "notification": {
            "title": "🚑 Emergency Vehicle Approaching",
            "body": notification.get("body", "Please clear the way for an ambulance."),
            "sound": "emergency_alert",
        },
        "data": notification,
        "priority": "high",
        "android": {"priority": "high"},
        "apns": {"headers": {"apns-priority": "10"}},
    }
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.post(FCM_ENDPOINT, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except requests.RequestException as e:
            logger.warning(f"FCM attempt {attempt + 1} failed: {e}")
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)  # exponential backoff
    return {"success": 0, "failure": len(registration_tokens)}


def _determine_direction(
    civilian_loc: GPSCoordinate,
    ambulance_loc: GPSCoordinate,
    ambulance_heading: float | None,
) -> AlertDirection:
    """Determine which way civilian should move to clear the path."""
    if ambulance_heading is None:
        return AlertDirection.PULL_OVER
    bearing_to_civilian = bearing_degrees(ambulance_loc, civilian_loc)
    delta = (bearing_to_civilian - ambulance_heading + 360) % 360
    if 45 <= delta < 180:
        return AlertDirection.RIGHT
    elif 180 <= delta < 315:
        return AlertDirection.LEFT
    return AlertDirection.PULL_OVER


def _get_civilian_vehicles_in_radius(
    route_waypoints: List[GPSCoordinate],
    radius_m: float,
) -> List[Dict]:
    """
    Query DynamoDB for civilian vehicles within radius of route.
    In production: uses a DynamoDB geo-index or PostGIS query.
    """
    try:
        # Scan is used here for Local/Dev; prod implementation uses geo index
        resp = location_table.scan(
            FilterExpression="vehicleType = :t",
            ExpressionAttributeValues={":t": "CIVILIAN"},
            Limit=10000,
        )
        items = resp.get("Items", [])

        nearby = []
        for item in items:
            try:
                coord = GPSCoordinate(
                    latitude=float(item["latitude"]),
                    longitude=float(item["longitude"]),
                    timestamp=datetime.now(timezone.utc),
                )
                if is_within_corridor(coord, route_waypoints, radius_m):
                    nearby.append({
                        "vehicleId": item["vehicleId"],
                        "fcmToken": item.get("fcmToken", ""),
                        "latitude": float(item["latitude"]),
                        "longitude": float(item["longitude"]),
                    })
            except Exception:
                continue
        return nearby
    except ClientError as e:
        logger.error(f"DynamoDB scan error: {e}")
        return []


def _log_alert(alert_log: AlertLog) -> None:
    try:
        item = alert_log.dict()
        item["ttl"] = int(
            (alert_log.sent_at.timestamp()) + 86400  # 24-hour TTL
        )
        alert_table.put_item(Item={k: str(v) if v is not None else None for k, v in item.items()})
    except Exception as e:
        logger.error(f"Alert log error: {e}")


# ---------------------------------------------------------------------------
# Route Handlers
# ---------------------------------------------------------------------------

def _handle_send(body: Dict) -> Dict:
    """POST /alert/send"""
    corridor_id = body.get("corridorId")
    waypoints_raw = body.get("routeWaypoints", [])
    ambulance_loc_raw = body.get("ambulanceLocation", {})
    eta_seconds = body.get("etaSeconds", 120)

    if not corridor_id or not waypoints_raw:
        return {"statusCode": 400, "body": json.dumps({"error": "corridorId and routeWaypoints required"})}

    try:
        waypoints = [GPSCoordinate(**w) for w in waypoints_raw]
        ambulance_loc = GPSCoordinate(**ambulance_loc_raw)
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Bad data: {e}"})}

    radius_m = settings.alert_radius_meters
    vehicles = _get_civilian_vehicles_in_radius(waypoints, radius_m)

    start_time = time.time()
    successful = 0
    failed = 0

    # Batch into groups of 1000
    for i in range(0, max(1, len(vehicles)), _MAX_BATCH_SIZE):
        batch = vehicles[i:i + _MAX_BATCH_SIZE]
        tokens = [v["fcmToken"] for v in batch if v.get("fcmToken")]

        direction = AlertDirection.PULL_OVER
        if batch:
            veh_coord = GPSCoordinate(
                latitude=batch[0]["latitude"],
                longitude=batch[0]["longitude"],
                timestamp=datetime.now(timezone.utc),
            )
            direction = _determine_direction(veh_coord, ambulance_loc, ambulance_loc.heading)

        # Generate multilingual alerts using Bedrock
        bedrock = get_bedrock_service()
        alerts = bedrock.generate_multilingual_alert(direction.value, eta_seconds)
        
        # Combine alerts into a single body or pick primary language
        # For this implementation, we'll provide the data in FCM and a combined body
        combined_body = f"EN: {alerts.get('en')}\nHI: {alerts.get('hi')}\nBN: {alerts.get('bn')}"

        notification_data = {
            "corridorId": corridor_id,
            "direction": direction.value,
            "etaSeconds": str(eta_seconds),
            "body": alerts.get("en", f"Please move {direction.value.lower().replace('_', ' ')} – ambulance in {eta_seconds}s"),
            "alerts": json.dumps(alerts)  # Send all languages in data payload
        }

        if tokens:

            fcm_result = _send_fcm(tokens, notification_data)
            successful += fcm_result.get("success", 0)
            failed += fcm_result.get("failure", 0)

        # Log each vehicle
        for veh in batch:
            log = AlertLog(
                alert_id=str(uuid.uuid4()),
                corridor_id=corridor_id,
                recipient_vehicle_id=veh["vehicleId"],
                sent_at=datetime.now(timezone.utc),
                delivery_status=DeliveryStatus.SENT,
            )
            _log_alert(log)

    delivery_time_ms = (time.time() - start_time) * 1000
    result = AlertResult(
        total_sent=len(vehicles),
        successful=successful,
        failed=failed,
        delivery_time_ms=delivery_time_ms,
    )

    logger.info(json.dumps({
        "event": "alerts_sent",
        "corridorId": corridor_id,
        "total": result.total_sent,
        "success": result.successful,
        "failed": result.failed,
    }))

    return {"statusCode": 200, "body": json.dumps(result.dict())}


def _handle_update(corridor_id: str, body: Dict) -> Dict:
    """PATCH /alert/update/{corridorId} – route changed, re-send to newly affected vehicles."""
    # Delegate to send with updated waypoints
    return _handle_send({**body, "corridorId": corridor_id})


def _handle_cancel(corridor_id: str) -> Dict:
    """DELETE /alert/cancel/{corridorId} – corridor completed, send clearance."""
    # Retrieve affected vehicle IDs from alert log
    try:
        resp = alert_table.query(
            IndexName="corridorId-index",
            KeyConditionExpression="corridorId = :cid",
            ExpressionAttributeValues={":cid": corridor_id},
        )
        vehicles = [item["recipientVehicleId"] for item in resp.get("Items", [])]
        logger.info(f"Sending clearance to {len(vehicles)} vehicles for corridor {corridor_id}")

        # Send clearance FCM (no specific direction needed)
        tokens_placeholder: List[str] = []  # Would be real tokens from DB
        _send_fcm(tokens_placeholder, {
            "type": "CLEARANCE",
            "corridorId": corridor_id,
            "body": "✅ Emergency vehicle has passed. You may resume normal driving.",
        })

    except Exception as e:
        logger.error(f"Cancel error: {e}")

    return {"statusCode": 200, "body": json.dumps({"cancelled": True, "corridorId": corridor_id})}


def handler(event: Dict, context: Any) -> Dict:
    path = event.get("path", "")
    method = event.get("httpMethod", "POST")
    path_params = event.get("pathParameters") or {}
    corridor_id = path_params.get("corridorId", "")

    try:
        body = json.loads(event.get("body", "{}") or "{}")
    except json.JSONDecodeError:
        body = {}

    if path.endswith("/send") and method == "POST":
        resp = _handle_send(body)
    elif "update" in path and method in ("PATCH", "PUT") and corridor_id:
        resp = _handle_update(corridor_id, body)
    elif "cancel" in path and method == "DELETE" and corridor_id:
        resp = _handle_cancel(corridor_id)
    else:
        resp = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    resp["headers"] = {"Content-Type": "application/json"}
    return resp
