import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
"""
SankatMitra – GPS Tracking Lambda Handler
POST /gps/update          → receive GPS fix from ambulance
GET  /gps/{vehicleId}     → get current location
GET  /gps/{vehicleId}/history → get location history
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table
    from mypy_boto3_sns import SNSClient

import boto3
from botocore.exceptions import ClientError

from mitrashared.config import get_settings
from mitrashared.models import GPSCoordinate, GPSData, SignalQuality, VehicleLocation
from mitrashared.anomaly_detector import validate_gps_signal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = get_settings()
dynamodb: DynamoDBServiceResource = boto3.resource("dynamodb", region_name=settings.aws_region)
location_table: Table = dynamodb.Table(settings.dynamo_location_table)
sns: SNSClient = boto3.client("sns", region_name=settings.aws_region)

MAX_HISTORY_ITEMS = 1000


def _float_to_decimal(d: dict) -> dict:
    """DynamoDB requires Decimal for floats."""
    result = {}
    for k, v in d.items():
        if isinstance(v, float):
            result[k] = Decimal(str(v))
        elif isinstance(v, dict):
            result[k] = _float_to_decimal(v)
        else:
            result[k] = v
    return result


def _determine_signal_quality(satellite_count: int, accuracy: float) -> SignalQuality:
    if satellite_count >= 8 and accuracy <= 5:
        return SignalQuality.HIGH
    elif satellite_count >= 4 and accuracy <= 15:
        return SignalQuality.MEDIUM
    return SignalQuality.LOW


def _get_location_history(vehicle_id: str, limit: int = 10) -> List[GPSCoordinate]:
    """Fetch recent location history from DynamoDB."""
    try:
        resp = location_table.query(
            KeyConditionExpression="vehicleId = :vid",
            ExpressionAttributeValues={":vid": vehicle_id},
            ScanIndexForward=False,
            Limit=limit,
        )
        items = resp.get("Items", [])
        coords = []
        for item in reversed(items):  # oldest first
            coords.append(GPSCoordinate(
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                accuracy=float(item.get("accuracy", 10.0)),
                timestamp=datetime.fromisoformat(item["timestamp"]),
                speed=float(item["speed"]) if item.get("speed") else None,
                heading=float(item["heading"]) if item.get("heading") else None,
            ))
        return coords
    except ClientError as e:
        logger.error(f"DynamoDB query error: {e}")
        return []


def _handle_update(body: Dict) -> Dict:
    """POST /gps/update – validate + store GPS fix."""
    vehicle_id = body.get("vehicleId")
    if not vehicle_id:
        return {"statusCode": 400, "body": json.dumps({"error": "vehicleId required"})}

    try:
        coord = GPSCoordinate(**body.get("coordinate", {}))
        gps_data = GPSData(
            coordinate=coord,
            satellite_count=body.get("satelliteCount", 6),
            signal_strength=body.get("signalStrength", -80.0),
            cell_tower_data=body.get("cellTowerData"),
        )
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Invalid GPS data: {e}"})}

    # Fetch history for anomaly detection
    history = _get_location_history(vehicle_id, limit=5)

    # GPS Anomaly Detection (Property 10, 11)
    validation = validate_gps_signal(gps_data, history)
    if not validation.is_valid:
        logger.warning(json.dumps({
            "event": "gps_anomaly",
            "vehicleId": vehicle_id,
            "confidence": validation.confidence_score,
            "flags": [f.dict() for f in validation.flags],
        }))
        # Notify spoofing detection via SNS
        if settings.sns_spoofing_topic_arn:
            sns.publish(
                TopicArn=settings.sns_spoofing_topic_arn,
                Message=json.dumps({
                    "vehicleId": vehicle_id,
                    "confidence": validation.confidence_score,
                    "flags": [f.dict() for f in validation.flags],
                    "timestamp": coord.timestamp.isoformat(),
                }),
                Subject="GPS Spoofing Detected",
            )

    # Store location in DynamoDB (even suspicious ones – for audit)
    signal_quality = _determine_signal_quality(
        gps_data.satellite_count, coord.accuracy
    )
    item = {
        "vehicleId": vehicle_id,
        "timestamp": coord.timestamp.isoformat(),
        "latitude": coord.latitude,
        "longitude": coord.longitude,
        "accuracy": coord.accuracy,
        "speed": coord.speed,
        "heading": coord.heading,
        "signalQuality": signal_quality.value,
        "spoofingConfidence": float(validation.confidence_score),
        "isValid": validation.is_valid,
        "vehicleType": body.get("type", "AMBULANCE"),
        "fcmToken": body.get("fcmToken"),
    }
    try:
        location_table.put_item(Item=_float_to_decimal(item))
    except ClientError as e:
        logger.error(f"DynamoDB put error: {e}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "stored": True,
            "signalQuality": signal_quality.value,
            "spoofingConfidence": validation.confidence_score,
            "isValid": validation.is_valid,
        }),
    }


def _handle_get_location(vehicle_id: str) -> Dict:
    """GET /gps/{vehicleId} – fetch latest location."""
    history = _get_location_history(vehicle_id, limit=1)
    if not history:
        return {"statusCode": 404, "body": json.dumps({"error": "No location data found"})}
    coord = history[-1]
    return {
        "statusCode": 200,
        "body": json.dumps({
            "vehicleId": vehicle_id,
            "coordinate": coord.dict(),
            "lastUpdate": coord.timestamp.isoformat(),
        }, default=str),
    }


def _handle_history(vehicle_id: str) -> Dict:
    """GET /gps/{vehicleId}/history – fetch last 100 points."""
    history = _get_location_history(vehicle_id, limit=100)
    return {
        "statusCode": 200,
        "body": json.dumps({
            "vehicleId": vehicle_id,
            "count": len(history),
            "history": [c.dict() for c in history],
        }, default=str),
    }


def handler(event: Dict, context: Any) -> Dict:
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "GET")
        path_params = event.get("pathParameters") or {}
        vehicle_id = path_params.get("vehicleId", "")

        try:
            body = json.loads(event.get("body", "{}") or "{}")
        except json.JSONDecodeError:
            body = {}

        headers = {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST,GET,OPTIONS,DELETE,PATCH",
            "Access-Control-Allow-Headers": "Content-Type,Authorization"
        }

        if path.endswith("/update") and method == "POST":
            resp = _handle_update(body)
        elif path.endswith("/history") and method == "GET" and vehicle_id:
            resp = _handle_history(vehicle_id)
        elif method == "GET" and vehicle_id:
            resp = _handle_get_location(vehicle_id)
        else:
            resp = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

        resp["headers"] = headers
        return resp
    except Exception as e:
        import traceback
        error_msg = f"GPS Lambda Error: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "error": "Internal Server Error",
                "details": str(e) if settings.environment == "development" else "Unexpected error"
            })
        }
