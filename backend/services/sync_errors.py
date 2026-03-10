from __future__ import annotations

from typing import Any, Dict


def classify_sync_error(error: BaseException, *, consecutive_failure_count: int = 0) -> Dict[str, Any]:
    message = str(error).strip()
    lowered = message.lower()

    if any(token in lowered for token in ("authentication failed", "401", "unauthorized", "invalid credentials")):
        return {
            "category": "auth",
            "code": "garmin_invalid_credentials",
            "userMessage": "Garmin credentials need to be updated.",
            "retryable": False,
            "cooldownSeconds": None,
            "blocked": True,
        }

    if any(
        token in lowered
        for token in (
            "missing credentials",
            "credentials missing",
            "garmin not connected",
            "garmin account missing",
            "garmin credentials missing",
            "missing config",
            "config",
        )
    ):
        return {
            "category": "validation",
            "code": "sync_configuration_invalid",
            "userMessage": "Sync configuration is incomplete.",
            "retryable": False,
            "cooldownSeconds": None,
            "blocked": True,
        }

    if any(token in lowered for token in ("timeout", "timed out", "429", "rate limit", "temporary", "temporarily unavailable")):
        return {
            "category": "transient",
            "code": "garmin_temporary_error",
            "userMessage": "Temporary Garmin error, retry later.",
            "retryable": True,
            "cooldownSeconds": transient_cooldown_seconds(consecutive_failure_count),
            "blocked": False,
        }

    return {
        "category": "unknown",
        "code": "sync_unknown_error",
        "userMessage": "Sync failed unexpectedly.",
        "retryable": True,
        "cooldownSeconds": transient_cooldown_seconds(consecutive_failure_count),
        "blocked": False,
    }


def transient_cooldown_seconds(consecutive_failure_count: int) -> int:
    if consecutive_failure_count <= 1:
        return 15 * 60
    if consecutive_failure_count == 2:
        return 60 * 60
    return 6 * 60 * 60
