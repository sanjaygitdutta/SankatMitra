"""
SankatMitra – Authentication Service (Lambda Handler)
Lightweight version with zero external dependencies.
"""
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

from shared.config import get_settings
from shared.models import AuthResult, Credentials, TokenValidation
from shared.security import create_access_token, verify_token

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

settings = get_settings()

# Circuit Breaker state (simple in-memory for Lambda)
_circuit_open = False
_circuit_opened_at = 0
_CIRCUIT_TIMEOUT_S = 60

def _call_gov_db(credentials: Credentials) -> Dict:
    """Standard-library call to Gov DB."""
    global _circuit_open, _circuit_opened_at

    if _circuit_open:
        if time.time() - _circuit_opened_at < _CIRCUIT_TIMEOUT_S:
            raise ConnectionError("Circuit breaker open")
        else:
            _circuit_open = False

    url = f"{settings.gov_db_api_url}/verify"
    data = json.dumps({
        "vehicleId": credentials.vehicle_id,
        "registrationNumber": credentials.registration_number,
        "agencyId": credentials.agency_id,
        "signature": credentials.digital_signature,
    }).encode()
    
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("X-API-Key", settings.gov_db_api_key)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.error(f"Gov DB call failed: {str(e)}")
        _circuit_open = True
        _circuit_opened_at = time.time()
        raise

def _handle_login(body: Dict) -> Dict:
    """Authenticate a vehicle and issue a JWT."""
    try:
        # 1. Validate Input
        try:
            creds = Credentials.model_validate(body)
        except Exception as e:
            return {"statusCode": 400, "body": json.dumps({"error": f"Invalid input: {str(e)}"}) }

        # 2. Check Local Database (DynamoDB)
        dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        table = dynamodb.Table(settings.dynamo_vehicle_table)
        
        try:
            resp = table.get_item(Key={"vehicleId": creds.vehicle_id})
            vehicle_data = resp.get("Item")
        except ClientError as e:
            logger.error(f"DynamoDB error: {e}")
            return {"statusCode": 500, "body": json.dumps({"error": "Database error"})}

        if not vehicle_data:
            return {"statusCode": 401, "body": json.dumps({"error": "Vehicle not registered"})}

        # 3. Check Gov DB (Bypass in development)
        if settings.environment != "development":
            try:
                gov_resp = _call_gov_db(creds)
                if not gov_resp.get("success"):
                    return {"statusCode": 403, "body": json.dumps({"error": "Gov verification failed"})}
            except Exception as e:
                return {"statusCode": 503, "body": json.dumps({"error": "Identity service unavailable"})}
        else:
            logger.info(f"Bypassing Gov DB check for {creds.vehicle_id} in {settings.environment}")

        # 4. Success - Issue Token
        token, expires_at = create_access_token(creds.vehicle_id)
        
        # Update last login
        try:
            table.update_item(
                Key={"vehicleId": creds.vehicle_id},
                UpdateExpression="SET lastAuthentication = :t",
                ExpressionAttributeValues={":t": datetime.now().isoformat()}
            )
        except: pass

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "token": token,
                "vehicle_type": vehicle_data.get("vehicleType", "AMBULANCE"),
                "expires_at": expires_at.isoformat()
            })
        }

    except Exception as e:
        logger.exception("Login handler failed")
        return {"statusCode": 500, "body": json.dumps({"error": "Internal error"})}

def _handle_validate(body: Dict) -> Dict:
    token = body.get("token")
    if not token:
        return {"statusCode": 400, "body": json.dumps({"error": "No token"})}
    try:
        payload = verify_token(token)
        return {
            "statusCode": 200,
            "body": json.dumps({"valid": True, "vehicle_id": payload.get("sub")})
        }
    except Exception as e:
        return {"statusCode": 401, "body": json.dumps({"valid": False, "error": str(e)})}

def _handle_revoke(body: Dict) -> Dict:
    # Minimal implementation for demo
    return {"statusCode": 200, "body": json.dumps({"success": True})}

def handler(event: Dict, context: Any) -> Dict:
    path = event.get("path", "")
    method = event.get("httpMethod", "POST")
    
    # Handle CORS Preflight
    if method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type,Authorization"
            }
        }

    try:
        body = json.loads(event.get("body") or "{}")
    except:
        body = {}

    if path.endswith("/login"): resp = _handle_login(body)
    elif path.endswith("/validate"): resp = _handle_validate(body)
    elif path.endswith("/revoke"): resp = _handle_revoke(body)
    else: resp = {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    resp.setdefault("headers", {})
    resp["headers"].update({
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,Authorization"
    })
    return resp
