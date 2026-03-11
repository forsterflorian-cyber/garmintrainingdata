from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from observability import ServiceError

if TYPE_CHECKING:
    from garmin_session_store import GarminAccount


APP_PHASE_DASHBOARD = "dashboard"
APP_PHASE_GARMIN_SETUP = "garmin_setup"
APP_PHASE_SETTINGS = "settings"

GARMIN_STATE_MISSING = "missing"
GARMIN_STATE_READY = "ready"
GARMIN_STATE_ACTION_REQUIRED = "action_required"

BLOCKED_SYNC_REASONS_REQUIRING_RECONNECT = {
    "blocked",
    "credentials_invalid",
    "credentials_missing",
}


def build_authenticated_app_state(
    account: Optional["GarminAccount"],
    sync_status: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    garmin = evaluate_garmin_setup(account, sync_status)
    phase = APP_PHASE_DASHBOARD
    if garmin["needsOnboarding"]:
        phase = APP_PHASE_GARMIN_SETUP
    elif garmin["needsReconnect"]:
        phase = APP_PHASE_SETTINGS

    return {
        "phase": phase,
        "dashboardAccessible": phase == APP_PHASE_DASHBOARD,
        "settingsAccessible": phase == APP_PHASE_SETTINGS or garmin["isUsable"],
        "recommendedRoute": _route_name_for_phase(phase),
        "garmin": garmin,
        "sync": sync_status or {},
    }


def evaluate_garmin_setup(
    account: Optional["GarminAccount"],
    sync_status: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    sync_status = sync_status or {}
    if account is None:
        return _garmin_state(
            connection_state=GARMIN_STATE_MISSING,
            is_configured=False,
            is_usable=False,
            needs_onboarding=True,
            needs_reconnect=False,
            status_code="credentials_missing",
            message="Add your Garmin account before entering the dashboard.",
        )

    has_email = bool(account.garmin_email_enc)
    has_password = bool(account.garmin_password_enc)
    if not has_email and not has_password:
        return _garmin_state(
            connection_state=GARMIN_STATE_MISSING,
            is_configured=False,
            is_usable=False,
            needs_onboarding=True,
            needs_reconnect=False,
            status_code="credentials_missing",
            message="Add your Garmin account before entering the dashboard.",
        )

    if has_email != has_password:
        return _garmin_state(
            connection_state=GARMIN_STATE_ACTION_REQUIRED,
            is_configured=False,
            is_usable=False,
            needs_onboarding=False,
            needs_reconnect=True,
            status_code="credentials_incomplete",
            message="Stored Garmin credentials are incomplete. Reconnect Garmin in settings.",
        )

    try:
        credentials = account.credentials()
    except ServiceError:
        return _garmin_state(
            connection_state=GARMIN_STATE_ACTION_REQUIRED,
            is_configured=False,
            is_usable=False,
            needs_onboarding=False,
            needs_reconnect=True,
            status_code="credentials_unreadable",
            message="Stored Garmin credentials could not be read. Reconnect Garmin in settings.",
        )

    if not credentials:
        return _garmin_state(
            connection_state=GARMIN_STATE_ACTION_REQUIRED,
            is_configured=False,
            is_usable=False,
            needs_onboarding=False,
            needs_reconnect=True,
            status_code="credentials_missing",
            message="Stored Garmin credentials are missing. Reconnect Garmin in settings.",
        )

    email, password = credentials
    if not email.strip() or not password.strip():
        return _garmin_state(
            connection_state=GARMIN_STATE_ACTION_REQUIRED,
            is_configured=False,
            is_usable=False,
            needs_onboarding=False,
            needs_reconnect=True,
            status_code="credentials_empty",
            message="Stored Garmin credentials are empty. Reconnect Garmin in settings.",
        )

    sync_state = str(sync_status.get("syncState") or "")
    sync_reason = str(sync_status.get("statusReason") or "")
    if sync_state == "blocked" or sync_reason in BLOCKED_SYNC_REASONS_REQUIRING_RECONNECT:
        return _garmin_state(
            connection_state=GARMIN_STATE_ACTION_REQUIRED,
            is_configured=True,
            is_usable=False,
            needs_onboarding=False,
            needs_reconnect=True,
            status_code=sync_reason or "blocked",
            message=_blocked_message(sync_status),
        )

    message = "Garmin is connected."
    if sync_state == "error":
        message = sync_status.get("lastErrorMessage") or "Garmin sync needs attention. Review sync status in the dashboard."
    elif sync_state == "stale":
        message = "Garmin is connected. Data will refresh on the next sync."
    elif sync_state == "never_synced":
        message = "Garmin is connected. The first sync will populate the dashboard."

    return _garmin_state(
        connection_state=GARMIN_STATE_READY,
        is_configured=True,
        is_usable=True,
        needs_onboarding=False,
        needs_reconnect=False,
        status_code=sync_reason or "ready",
        message=str(message),
    )


def _blocked_message(sync_status: Dict[str, Any]) -> str:
    error_message = sync_status.get("lastErrorMessage")
    if isinstance(error_message, str) and error_message.strip():
        return error_message.strip()
    return "Garmin needs to be reconnected before the dashboard can load."


def _garmin_state(
    *,
    connection_state: str,
    is_configured: bool,
    is_usable: bool,
    needs_onboarding: bool,
    needs_reconnect: bool,
    status_code: str,
    message: str,
) -> Dict[str, Any]:
    return {
        "connectionState": connection_state,
        "isConfigured": is_configured,
        "isUsable": is_usable,
        "needsOnboarding": needs_onboarding,
        "needsReconnect": needs_reconnect,
        "statusCode": status_code,
        "message": message,
    }


def _route_name_for_phase(phase: str) -> str:
    if phase == APP_PHASE_GARMIN_SETUP:
        return "garminSetup"
    if phase == APP_PHASE_SETTINGS:
        return "settings"
    return "dashboard"
