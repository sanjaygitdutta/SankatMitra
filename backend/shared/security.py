"""
SankatMitra – JWT Security Utilities
"""
from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from .config import get_settings

settings = get_settings()


def create_access_token(vehicle_id: str, vehicle_type: str = "AMBULANCE") -> tuple[str, datetime]:
    """Create a signed JWT for an authenticated vehicle."""
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours)
    payload = {
        "sub": vehicle_id,
        "vehicle_type": vehicle_type,
        "iat": datetime.now(timezone.utc),
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def verify_token(token: str) -> dict:
    """
    Verify and decode a JWT.
    Returns the decoded payload or raises jwt.PyJWTError.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": True},
    )


def extract_vehicle_id(token: str) -> Optional[str]:
    """Extract vehicle_id from a bearer token without raising on error."""
    try:
        payload = verify_token(token)
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def verify_digital_signature(vehicle_id: str, registration_number: str, signature: str) -> bool:
    """
    Verify the digital signature provided by the ambulance app.
    In production this would use asymmetric keys from the government PKI.
    Here we use HMAC-SHA256 as a deterministic stand-in for testing.
    """
    expected = hmac.new(
        settings.jwt_secret_key.encode(),
        f"{vehicle_id}:{registration_number}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def token_from_header(authorization_header: str) -> Optional[str]:
    """Extract bearer token from 'Authorization: Bearer <token>' header."""
    if not authorization_header:
        return None
    parts = authorization_header.split(" ")
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None
