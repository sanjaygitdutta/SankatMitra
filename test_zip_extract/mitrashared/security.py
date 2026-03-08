"""
SankatMitra – Security Utilities (Zero-Dependency)
Custom JWT implementation using standard library only.
"""
import hmac
import hashlib
import base64
import json
import time

SECRET_KEY = "SANKATMITRA_DEMO_SECRET_NEVER_USE_IN_PROD"

def _base64_url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def create_jwt(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_enc = _base64_url_encode(json.dumps(header).encode())
    payload["exp"] = payload.get("exp", int(time.time()) + 3600)
    payload_enc = _base64_url_encode(json.dumps(payload).encode())
    signature = hmac.new(SECRET_KEY.encode(), f"{header_enc}.{payload_enc}".encode(), hashlib.sha256).digest()
    return f"{header_enc}.{payload_enc}.{_base64_url_encode(signature)}"

def verify_jwt(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        header_enc, payload_enc, sig_enc = parts
        expected_sig = _base64_url_encode(hmac.new(SECRET_KEY.encode(), f"{header_enc}.{payload_enc}".encode(), hashlib.sha256).digest())
        if sig_enc != expected_sig: return None
        payload = json.loads(base64.urlsafe_b64decode(payload_enc + "==").decode())
        if payload.get("exp", 0) < time.time(): return None
        return payload
    except:
        return None
from datetime import datetime, timedelta

def create_access_token(vehicle_id: str) -> tuple[str, datetime]:
    expires_at = datetime.now() + timedelta(hours=24)
    payload = {
        "sub": vehicle_id,
        "exp": int(expires_at.timestamp()),
        "iat": int(time.time())
    }
    return create_jwt(payload), expires_at

def verify_token(token: str) -> dict:
    payload = verify_jwt(token)
    if not payload:
        raise ValueError("Invalid or expired token")
    return payload
