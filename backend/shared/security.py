"""
SankatMitra – Standard Library Security Utilities
(No external dependencies for Lambda compatibility)
"""
import hmac
import hashlib
import json
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import get_settings

settings = get_settings()

def _base64_url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _base64_url_decode(data: str) -> bytes:
    pad = "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)

def create_access_token(vehicle_id: str, vehicle_type: str = "AMBULANCE") -> tuple[str, datetime]:
    """Create a signed HS256 JWT using standard library."""
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": vehicle_id,
        "vehicle_type": vehicle_type,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    
    msg = f"{_base64_url_encode(json.dumps(header).encode())}.{_base64_url_encode(json.dumps(payload).encode())}"
    sig = hmac.new(settings.jwt_secret_key.encode(), msg.encode(), hashlib.sha256).digest()
    token = f"{msg}.{_base64_url_encode(sig)}"
    return token, expires_at


def verify_token(token: str) -> dict:
    """Verify an HS256 JWT using standard library."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")
            
        msg = f"{parts[0]}.{parts[1]}"
        expected_sig = _base64_url_encode(hmac.new(settings.jwt_secret_key.encode(), msg.encode(), hashlib.sha256).digest())
        
        if not hmac.compare_digest(expected_sig, parts[2]):
            raise ValueError("Invalid signature")
            
        payload = json.loads(_base64_url_decode(parts[1]))
        if payload.get("exp") < datetime.now(timezone.utc).timestamp():
            raise ValueError("Token expired")
            
        return payload
    except Exception as e:
        raise ValueError(f"Token verification failed: {str(e)}")


def extract_vehicle_id(token: str) -> Optional[str]:
    try:
        payload = verify_token(token)
        return payload.get("sub")
    except:
        return None


def verify_digital_signature(vehicle_id: str, registration_number: str, signature: str) -> bool:
    expected = hmac.new(
        settings.jwt_secret_key.encode(),
        f"{vehicle_id}:{registration_number}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def token_from_header(authorization_header: str) -> Optional[str]:
    if not authorization_header:
        return None
    parts = authorization_header.split(" ")
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None
