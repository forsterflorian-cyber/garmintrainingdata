import os
import logging
from datetime import datetime, timezone
from functools import wraps

import jwt
from flask import jsonify, request
from jwt import PyJWKClient

from observability import ErrorCategory, get_logger, log_event, log_exception

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
SUPPORTED_JWT_ALGORITHMS = {"HS256", "RS256", "ES256"}
LOGGER = get_logger(__name__)


def _get_jwks_client() -> PyJWKClient:
    """Get JWKS client without unsafe caching."""
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
    """Verify JWT token with full validation."""
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get("alg")

        if algorithm not in SUPPORTED_JWT_ALGORITHMS:
            raise jwt.InvalidTokenError(f"unsupported token algorithm: {algorithm}")

        if algorithm == "HS256":
            if not SUPABASE_JWT_SECRET:
                raise RuntimeError("SUPABASE_JWT_SECRET is required for HS256 token verification.")
            key = SUPABASE_JWT_SECRET
        else:
            # Remove unsafe caching - create new client each time
            jwks_client = _get_jwks_client()
            key = jwks_client.get_signing_key_from_jwt(token).key

        # Enable full validation with audience, expiration, etc.
        payload = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            options={
                "verify_aud": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
                "require": ["exp", "iat", "sub"],
            },
            audience=SUPABASE_ANON_KEY if SUPABASE_ANON_KEY else None,
            issuer=f"{SUPABASE_URL}/auth/v1" if SUPABASE_URL else None,
        )

        # Additional validation
        if not payload.get("sub"):
            raise jwt.InvalidTokenError("missing token subject")

        # Check token expiration
        exp = payload.get("exp")
        if exp and datetime.fromtimestamp(exp, timezone.utc) < datetime.now(timezone.utc):
            raise jwt.InvalidTokenError("token expired")

        # Check issued at time (not in the future)
        iat = payload.get("iat")
        if iat and datetime.fromtimestamp(iat, timezone.utc) > datetime.now(timezone.utc):
            raise jwt.InvalidTokenError("token issued in the future")

        return payload

    except jwt.ExpiredSignatureError:
        raise jwt.InvalidTokenError("token expired")
    except jwt.InvalidAudienceError:
        raise jwt.InvalidTokenError("invalid token audience")
    except jwt.InvalidIssuerError:
        raise jwt.InvalidTokenError("invalid token issuer")
    except jwt.ImmatureSignatureError:
        raise jwt.InvalidTokenError("token not yet valid")
    except jwt.InvalidSignatureError:
        raise jwt.InvalidTokenError("invalid token signature")
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.AUTH,
            event="auth.token_verification_failed",
            message="Token verification failed.",
            exc=exc,
        )
        raise jwt.InvalidTokenError(f"token verification failed: {str(exc)}")


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
