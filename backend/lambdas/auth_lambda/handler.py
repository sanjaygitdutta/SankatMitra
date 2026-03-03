"""
SankatMitra – Authentication Lambda Handler
POST /auth/login   → authenticates vehicle, issues JWT
POST /auth/validate → validates existing JWT
POST /auth/revoke  → revokes vehicle access
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_dynamodb import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table

import boto3
import requests
from botocore.exceptions import ClientError

from backend.shared.config import get_settings
from backend.shared.models import AuthResult, Credentials, TokenValidation, VehicleStatus
from backend.shared.security import create_access_token, verify_token

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = get_settings()
dynamodb: DynamoDBServiceResource = boto3.resource("dynamodb", region_name=settings.aws_region)
vehicle_table: Table = dynamodb.Table(settings.dynamo_vehicle_table)


# ---------------------------------------------------------------------------
# Government DB helpers (with circuit breaker + retry)
# ---------------------------------------------------------------------------

_circuit_open = False
_circuit_opened_at: float = 0.0
_CIRCUIT_TIMEOUT_S = 300  # re-try gov DB after 5 minutes


def _verify_with_gov_db(credentials: Credentials) -> bool:
    """
    Validates vehicle credentials against the government EMS database.
    Retries up to 3 times with exponential back-off (1 s, 2 s, 4 s).
    Implements circuit-breaker: opens after 3 consecutive failures.
    """
    global _circuit_open, _circuit_opened_at

    # Check circuit breaker
    if _circuit_open:
        if time.time() - _circuit_opened_at < _CIRCUIT_TIMEOUT_S:
            logger.warning("Circuit breaker OPEN – skipping gov DB call")
            raise ConnectionError("Government database circuit breaker is open")
        else:
            _circuit_open = False  # half-open: try again

    consecutive_failures = 0
    for attempt, delay in enumerate(settings.auth_retry_delays, start=1):
        try:
            resp = requests.post(
                f"{settings.gov_db_api_url}/verify",
                json={
                    "vehicleId": credentials.vehicle_id,
                    "registrationNumber": credentials.registration_number,
                    "agencyId": credentials.agency_id,
                    "signature": credentials.digital_signature,
                },
                headers={"X-API-Key": settings.gov_db_api_key},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                _circuit_open = False
                return data.get("valid", False)
            # 4xx → invalid, no retry needed
            if 400 <= resp.status_code < 500:
                return False
        except (requests.ConnectionError, requests.Timeout) as exc:
            consecutive_failures += 1
            logger.warning(f"Gov DB attempt {attempt} failed: {exc}")
            if attempt < len(settings.auth_retry_delays):
                time.sleep(delay)

    # All retries exhausted – open circuit
    _circuit_open = True
    _circuit_opened_at = time.time()
    raise ConnectionError("Government database unreachable after retries")


def _get_cached_auth(vehicle_id: str) -> bool | None:
    """Check Redis cache for a recent successful authentication."""
    try:
        import redis
        r = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
        value = r.get(f"auth:{vehicle_id}")
        return value == "ok" if value is not None else None
    except Exception:
        return None


def _cache_auth(vehicle_id: str) -> None:
    try:
        import redis
        r = redis.Redis(host=settings.redis_host, port=settings.redis_port, decode_responses=True)
        r.setex(f"auth:{vehicle_id}", settings.auth_cache_ttl_minutes * 60, "ok")
    except Exception:
        pass  # Cache failure should not block authentication


def _get_vehicle_from_dynamo(vehicle_id: str) -> Dict | None:
    try:
        resp = vehicle_table.get_item(Key={"vehicleId": vehicle_id})
        return resp.get("Item")
    except ClientError as e:
        logger.error(f"DynamoDB error: {e}")
        return None


def _log_auth_attempt(vehicle_id: str, success: bool, error_code: str | None = None) -> None:
    """Property 35: Log every auth attempt with timestamp, vehicle ID, and result."""
    logger.info(
        json.dumps({
            "event": "auth_attempt",
            "vehicle_id": vehicle_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "error_code": error_code,
        })
    )


# ---------------------------------------------------------------------------
# Route Handlers
# ---------------------------------------------------------------------------

def _handle_login(body: Dict) -> Dict:
    """POST /auth/login"""
    try:
        credentials = Credentials(**body)
    except Exception as e:
        return {"statusCode": 400, "body": json.dumps({"error": f"Invalid request: {e}"})}

    # Check cache first
    cached = _get_cached_auth(credentials.vehicle_id)
    if cached:
        token, expires_at = create_access_token(credentials.vehicle_id)
        _log_auth_attempt(credentials.vehicle_id, True)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "token": token,
                "vehicleType": "AMBULANCE",
                "expiresAt": expires_at.isoformat(),
            }),
        }

    # Validate against DynamoDB local record first
    vehicle = _get_vehicle_from_dynamo(credentials.vehicle_id)
    if not vehicle:
        _log_auth_attempt(credentials.vehicle_id, False, "INVALID_VEHICLE_ID")
        return {"statusCode": 401, "body": json.dumps({"success": False, "errorCode": "INVALID_VEHICLE_ID"})}

    if vehicle.get("status") == VehicleStatus.SUSPENDED:
        _log_auth_attempt(credentials.vehicle_id, False, "SUSPENDED_VEHICLE")
        return {"statusCode": 403, "body": json.dumps({"success": False, "errorCode": "SUSPENDED_VEHICLE"})}

    if vehicle.get("status") == VehicleStatus.REVOKED:
        _log_auth_attempt(credentials.vehicle_id, False, "REVOKED_VEHICLE")
        return {"statusCode": 403, "body": json.dumps({"success": False, "errorCode": "REVOKED_VEHICLE"})}

    # Call government database
    try:
        gov_valid = _verify_with_gov_db(credentials)
    except ConnectionError as e:
        logger.error(f"Gov DB unavailable: {e}")
        _log_auth_attempt(credentials.vehicle_id, False, "GOV_DB_UNAVAILABLE")
        return {"statusCode": 503, "body": json.dumps({"success": False, "errorCode": "GOV_DB_UNAVAILABLE"})}

    if not gov_valid:
        _log_auth_attempt(credentials.vehicle_id, False, "INVALID_SIGNATURE")
        return {"statusCode": 401, "body": json.dumps({"success": False, "errorCode": "INVALID_SIGNATURE"})}

    # Issue JWT and cache
    token, expires_at = create_access_token(credentials.vehicle_id)
    _cache_auth(credentials.vehicle_id)

    # Update last authentication timestamp in DynamoDB
    vehicle_table.update_item(
        Key={"vehicleId": credentials.vehicle_id},
        UpdateExpression="SET lastAuthentication = :ts",
        ExpressionAttributeValues={":ts": datetime.now(timezone.utc).isoformat()},
    )

    _log_auth_attempt(credentials.vehicle_id, True)
    return {
        "statusCode": 200,
        "body": json.dumps({
            "success": True,
            "token": token,
            "vehicleType": "AMBULANCE",
            "expiresAt": expires_at.isoformat(),
        }),
    }


def _handle_validate(body: Dict) -> Dict:
    """POST /auth/validate"""
    token = body.get("token")
    if not token:
        return {"statusCode": 400, "body": json.dumps({"error": "token required"})}
    try:
        payload = verify_token(token)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "valid": True,
                "vehicleId": payload["sub"],
                "expiresAt": datetime.fromtimestamp(payload["exp"], tz=timezone.utc).isoformat(),
            }),
        }
    except Exception as e:
        return {"statusCode": 401, "body": json.dumps({"valid": False, "error": str(e)})}


def _handle_revoke(body: Dict) -> Dict:
    """POST /auth/revoke"""
    vehicle_id = body.get("vehicleId")
    reason = body.get("reason", "MANUAL_REVOKE")
    if not vehicle_id:
        return {"statusCode": 400, "body": json.dumps({"error": "vehicleId required"})}
    vehicle_table.update_item(
        Key={"vehicleId": vehicle_id},
        UpdateExpression="SET #s = :revoked",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":revoked": VehicleStatus.REVOKED},
    )
    logger.info(json.dumps({"event": "vehicle_revoked", "vehicleId": vehicle_id, "reason": reason}))
    return {"statusCode": 200, "body": json.dumps({"success": True})}


# ---------------------------------------------------------------------------
# Lambda Entry Point
# ---------------------------------------------------------------------------

def handler(event: Dict, context: Any) -> Dict:
    """AWS Lambda entry point for the Authentication Service."""
    path = event.get("path", "")
    method = event.get("httpMethod", "POST")
    try:
        body = json.loads(event.get("body", "{}") or "{}")
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON body"})}

    headers = {"Content-Type": "application/json"}

    if path.endswith("/login") and method == "POST":
        resp = _handle_login(body)
    elif path.endswith("/validate") and method == "POST":
        resp = _handle_validate(body)
    elif path.endswith("/revoke") and method == "POST":
        resp = _handle_revoke(body)
    else:
        resp = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    resp["headers"] = headers
    return resp
