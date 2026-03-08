import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

"""
SankatMitra - Spoofing Detection Lambda Handler
POST /spoof/validate - validate GPS authenticity, returns confidence score
POST /spoof/report   - report confirmed spoofing event to authorities
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table
    from mypy_boto3_sns import SNSClient

import boto3

from mitrashared.config import get_settings
from mitrashared.models import GPSCoordinate, GPSData
from mitrashared.anomaly_detector import validate_gps_signal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = get_settings()
dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
location_table = dynamodb.Table(settings.dynamo_location_table)
sns = boto3.client("sns", region_name=settings.aws_region)


def _get_history(vehicle_id: str, limit: int = 10):
    """Retrieve recent location history for a vehicle."""
    try:
        resp = location_table.query(
            KeyConditionExpression="vehicleId = :vid",
            ExpressionAttributeValues={":vid": vehicle_id},
            ScanIndexForward=False,
            Limit=limit,
        )
        items = resp.get("Items", [])
        history = []
        for item in reversed(items):
            history.append(GPSCoordinate(
                latitude=float(item["latitude"]),
                longitude=float(item["longitude"]),
                accuracy=float(item.get("accuracy", 10.0)),
                timestamp=datetime.fromisoformat(item["timestamp"]),
            ))
        return history
    except Exception as e:
        logger.error(f"History fetch error: {e}")
        return []


def _handle_validate(body: Dict) -> Dict:
    """POST /spoof/validate"""
    vehicle_id = body.get("vehicleId")
    if not vehicle_id:
        return {"statusCode": 400, "body": json.dumps({"error": "vehicleId required"})}

    try:
        raw_coord = body.get("coordinate", {})
        coord = GPSCoordinate(**raw_coord)
        cell_data = []
        gps_data = GPSData(
            vehicleId=vehicle_id,
            coordinate=coord,
            satellite_count=body.get("satelliteCount", 6),
            signal_strength=body.get("signalStrength", -80.0),
            cell_tower_data=cell_data,
        )
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Invalid data: {e}"})}

    history = _get_history(vehicle_id)
    result = validate_gps_signal(gps_data, history)

    # If rejected or review → publish SNS alert for corridor freeze
    if not result.is_valid and settings.sns_spoofing_topic_arn:
        try:
            sns.publish(
                TopicArn=settings.sns_spoofing_topic_arn,
                Message=json.dumps({
                    "vehicleId": vehicle_id,
                    "confidence": result.confidence_score,
                    "recommendation": result.recommendation,
                    "flags": [f.dict() for f in result.flags],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
                Subject=f"GPS Spoofing Alert – {vehicle_id}",
            )
        except Exception as e:
            logger.error(f"SNS publish error: {e}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "isValid": result.is_valid,
            "confidenceScore": result.confidence_score,
            "recommendation": result.recommendation,
            "flags": [f.dict() for f in result.flags],
        }),
    }


def _handle_report(body: Dict) -> Dict:
    """POST /spoof/report – log confirmed spoofing, alert authorities."""
    vehicle_id = body.get("vehicleId")
    if not vehicle_id:
        return {"statusCode": 400, "body": json.dumps({"error": "vehicleId required"})}

    logger.warning(json.dumps({
        "event": "spoofing_confirmed",
        "vehicleId": vehicle_id,
        "evidence": body.get("evidence", {}),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    if settings.sns_spoofing_topic_arn:
        try:
            sns.publish(
                TopicArn=settings.sns_spoofing_topic_arn,
                Message=json.dumps({
                    "type": "SPOOFING_CONFIRMED",
                    "vehicleId": vehicle_id,
                    "evidence": body.get("evidence", {}),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
                Subject=f"CONFIRMED Spoofing – {vehicle_id}",
            )
        except Exception as e:
            logger.error(f"SNS error: {e}")

    return {"statusCode": 200, "body": json.dumps({"reported": True})}


def handler(event: Dict, context: Any) -> Dict:
    path = event.get("path", "")
    method = event.get("httpMethod", "POST")
    try:
        body = json.loads(event.get("body", "{}") or "{}")
    except json.JSONDecodeError:
        body = {}

    if path.endswith("/validate") and method == "POST":
        resp = _handle_validate(body)
    elif path.endswith("/report") and method == "POST":
        resp = _handle_report(body)
    else:
        resp = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    resp["headers"] = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST,GET,OPTIONS,DELETE,PATCH",
        "Access-Control-Allow-Headers": "Content-Type,Authorization"
    }
    return resp
