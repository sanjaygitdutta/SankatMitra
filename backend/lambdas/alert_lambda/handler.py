"""
SankatMitra – Alert Distribution Lambda Handler
Zero-Dependency Version (Standard Library only)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, TYPE_CHECKING

import boto3
from botocore.exceptions import ClientError

from shared.config import get_settings
from shared.models import Alert, AlertDirection, UrgencyLevel, GPSCoordinate
from shared.geo_utils import is_within_corridor, bearing_degrees
from shared.bedrock_service import get_bedrock_service

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = get_settings()
dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
alert_table = dynamodb.Table(settings.dynamo_alert_table)
location_table = dynamodb.Table(settings.dynamo_location_table)
sns = boto3.client("sns", region_name=settings.aws_region)

# FCM Push Notification Helper (Firebase)
FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send"
_MAX_BATCH_SIZE = 1000
_MAX_RETRIES = 3


def _send_fcm(registration_tokens: List[str], notification: Dict) -> Dict:
    """Send FCM push notification using standard library."""
    if not registration_tokens:
        return {"success": 0, "failure": 0}

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
    }
    
    data = json.dumps(payload).encode()
    req = urllib.request.Request(FCM_ENDPOINT, data=data, headers=headers, method="POST")

    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            logger.warning(f"FCM attempt {attempt + 1} failed: {e}")
            if attempt < _MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
    return {"success": 0, "failure": len(registration_tokens)}


def _determine_direction(
    civilian_loc: GPSCoordinate,
    ambulance_loc: GPSCoordinate,
    ambulance_heading: float | None,
) -> AlertDirection:
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
    try:
        resp = location_table.scan(
            FilterExpression="vehicleType = :t",
            ExpressionAttributeValues={":t": "CIVILIAN"},
            Limit=1000, # Reduced limit for demo safety
        )
        items = resp.get("Items", [])

        nearby = []
        for item in items:
            try:
                coord = GPSCoordinate(
                    latitude=float(item["latitude"]),
                    longitude=float(item["longitude"]),
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


def _handle_send(body: Dict) -> Dict:
    corridor_id = body.get("corridorId")
    waypoints_raw = body.get("routeWaypoints", [])
    ambulance_loc_raw = body.get("ambulanceLocation", {})
    eta_seconds = body.get("etaSeconds", 120)

    if not corridor_id or not waypoints_raw:
        return {"statusCode": 400, "body": json.dumps({"error": "corridorId and routeWaypoints required"})}

    waypoints = [GPSCoordinate.model_validate(w) for w in waypoints_raw]
    ambulance_loc = GPSCoordinate.model_validate(ambulance_loc_raw)

    vehicles = _get_civilian_vehicles_in_radius(waypoints, settings.alert_radius_meters)
    successful = 0
    failed = 0

    if vehicles:
        tokens = [v["fcmToken"] for v in vehicles if v.get("fcmToken")]
        direction = _determine_direction(
            GPSCoordinate(latitude=vehicles[0]["latitude"], longitude=vehicles[0]["longitude"]),
            ambulance_loc,
            ambulance_loc.heading
        )

        try:
            bedrock = get_bedrock_service()
            alerts = bedrock.generate_multilingual_alert(direction.value, eta_seconds)
        except:
            alerts = {"en": f"Move {direction.value.lower()} – ambulance in {eta_seconds}s"}

        notification_data = {
            "corridorId": corridor_id,
            "direction": direction.value,
            "etaSeconds": str(eta_seconds),
            "body": alerts.get("en", "Please clear the path"),
            "alerts": json.dumps(alerts)
        }

        fcm_result = _send_fcm(tokens, notification_data)
        successful = fcm_result.get("success", 0)
        failed = fcm_result.get("failure", 0)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "total_sent": len(vehicles),
            "successful": successful,
            "failed": failed
        })
    }

def handler(event: Dict, context: Any) -> Dict:
    path = event.get("path", "")
    method = event.get("httpMethod", "POST")
    body = json.loads(event.get("body", "{}") or "{}")

    if path.endswith("/send"): resp = _handle_send(body)
    elif "cancel" in path: resp = {"statusCode": 200, "body": "{}"} # Minimal for demo
    else: resp = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    resp["headers"] = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,Authorization"
    }
    return resp
