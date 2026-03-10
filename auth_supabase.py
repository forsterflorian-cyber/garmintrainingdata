import os
import logging
from functools import lru_cache, wraps

import jwt
from flask import jsonify, request
from jwt import PyJWKClient

from observability import ErrorCategory, get_logger, log_event, log_exception

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPPORTED_JWT_ALGORITHMS = {"HS256", "RS256", "ES256"}
LOGGER = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_jwks_client() -> PyJWKClient:
    if not SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is required for JWKS token verification.")
    return PyJWKClient(f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json")


def _extract_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[len("Bearer ") :].strip()
    return token or None


def _verify_token(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")

    if algorithm not in SUPPORTED_JWT_ALGORITHMS:
        raise jwt.InvalidTokenError("unsupported token algorithm")

    if algorithm == "HS256":
        if not SUPABASE_JWT_SECRET:
            raise RuntimeError("SUPABASE_JWT_SECRET is required for HS256 token verification.")
        key = SUPABASE_JWT_SECRET
    else:
        key = _get_jwks_client().get_signing_key_from_jwt(token).key

    payload = jwt.decode(
        token,
        key,
        algorithms=[algorithm],
        options={"verify_aud": False},
    )

    if not payload.get("sub"):
        raise jwt.InvalidTokenError("missing token subject")

    return payload


def require_user(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            log_event(
                LOGGER,
                logging.WARNING,
                category=ErrorCategory.AUTH,
                event="auth.missing_token",
                message="Bearer token missing.",
                path=request.path,
            )
            return jsonify({"error": "missing token"}), 401

        try:
            payload = _verify_token(token)
        except Exception as exc:
            log_exception(
                LOGGER,
                category=ErrorCategory.AUTH,
                event="auth.invalid_token",
                message="Bearer token verification failed.",
                exc=exc,
                level=logging.WARNING,
                path=request.path,
            )
            return jsonify({"error": "invalid token"}), 401

        request.user_id = payload["sub"]
        request.auth_payload = payload
        return f(*args, **kwargs)

    return wrapper
