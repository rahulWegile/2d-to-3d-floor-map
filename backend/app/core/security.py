import json
import time
import urllib.request

import jwt
from datetime import datetime, timedelta
from fastapi import Header, HTTPException
from app.core.config import (
    SECRET_KEY, ALGORITHM, AUTH_JWT_SECRET, AUTH_JWT_ALGORITHMS, AUTH_SERVICE_URL,
)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Claims checked (in order) for the user id. The CompleTech auth service may
# use a different claim than this service's own "sub".
_USER_ID_CLAIMS = ("sub", "id", "userId", "user_id", "_id")

def _extract_user_id(payload: dict):
    for claim in _USER_ID_CLAIMS:
        value = payload.get(claim)
        if value is not None:
            return str(value)
    return None

# token -> (user_id, cache_expiry). Caps auth-service introspection at one
# call per token instead of one per request.
_introspection_cache = {}

def _verify_via_auth_service(token: str):
    """Validate the token by asking the CompleTech auth service.

    POST /auth/refresh returns 200 only for a valid token, which lets this
    backend accept admin JWTs without knowing the signing secret. Once the
    auth service has vouched for the token, reading its claims unverified
    is safe.
    """
    if not AUTH_SERVICE_URL:
        return None

    now = time.time()
    cached = _introspection_cache.get(token)
    if cached and cached[1] > now:
        return cached[0]

    try:
        req = urllib.request.Request(
            AUTH_SERVICE_URL + "/auth/refresh",
            method="POST",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=8) as res:
            if res.status != 200:
                return None
    except Exception as e:
        print(f"[auth] introspection via {AUTH_SERVICE_URL}/auth/refresh failed: {e}")
        return None

    payload = jwt.decode(token, options={"verify_signature": False})
    user_id = _extract_user_id(payload)
    if user_id:
        # Cache until the token itself expires (fallback: 5 minutes).
        exp = payload.get("exp", now + 300)
        _introspection_cache[token] = (user_id, min(exp, now + 3600))
        if len(_introspection_cache) > 1000:
            _introspection_cache.clear()
    return user_id

def _decode_token(token: str):
    """Verify the token and return the user id, or None.

    Order: the CompleTech auth-service secret (admin session JWTs from
    completech-admin-web), then the legacy secret for tokens issued by this
    service's own /auth endpoints, then introspection against the auth
    service for admin tokens when no matching local secret is configured.
    Audience verification is disabled because this service is not the
    token's original audience.
    """
    candidates = []
    if AUTH_JWT_SECRET:
        candidates.append((AUTH_JWT_SECRET, AUTH_JWT_ALGORITHMS))
    candidates.append((SECRET_KEY, [ALGORITHM]))

    for secret, algorithms in candidates:
        try:
            payload = jwt.decode(
                token, secret, algorithms=algorithms,
                options={"verify_aud": False},
            )
        except Exception:
            continue
        user_id = _extract_user_id(payload)
        if user_id:
            return user_id

    return _verify_via_auth_service(token)

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    user_id = _decode_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id

def get_current_user_optional(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    return _decode_token(token)
