from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request

from auth_supabase import require_user
from backend.routes.dashboard import create_dashboard_blueprint
from backend.routes.settings import create_settings_blueprint
from backend.services.garmin_connection_service import GarminConnectionService
from backend.routes.sync import create_sync_blueprint
from backend.services.account_service import AccountService
from backend.services.app_flow_service import build_authenticated_app_state
from backend.services.sync_errors import classify_sync_error
from backend.services.sync_runner import SyncRunner
from backend.services.sync_status_service import SyncStatusService
from backend.validators import InputValidator, GarminCredentialsValidator
from dashboard_service import (
    build_prompt_from_payload,
    build_series,
    fetch_training_rows,
    mode_or_default,
    payload_for_date,
)
from garmin_hybrid_report_v62_supabase_ready import (
    export_client_session,
    load_client,
)
from garmin_session_store import GarminSessionStore
from observability import ErrorCategory, ServiceError, configure_structured_logging, get_logger, log_event, log_exception
from runtime_config import validate_server_runtime
from supabase_client import get_supabase_admin_client
from training_config import TRAINING_CONFIG


try:
    validate_server_runtime()
    supabase = get_supabase_admin_client()
except RuntimeError as exc:
    raise RuntimeError(f"Application startup failed. {exc}") from exc

store = GarminSessionStore(supabase)
garmin_connection_service = GarminConnectionService(
    session_store=store,
    load_client_fn=load_client,
    export_session_fn=export_client_session,
)
sync_status_service = SyncStatusService(supabase)
sync_runner = SyncRunner(supabase_client=supabase, session_store=store)
account_service = AccountService(supabase)
DEBUG_MODE = os.environ.get("APP_ENV", "development").lower() != "production"

app = Flask(__name__, template_folder="templates", static_folder="static")
configure_structured_logging(app.logger)
LOGGER = get_logger(__name__)


def _missing_public_config() -> List[str]:
    missing: List[str] = []
    if not os.environ.get("SUPABASE_URL"):
        missing.append("SUPABASE_URL")
    if not os.environ.get("SUPABASE_ANON_KEY"):
        missing.append("SUPABASE_ANON_KEY")
    return missing


def _garmin_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if "Authentication failed" in message or "401 Client Error" in message:
        return "Garmin sign-in failed. Check your Garmin email and password."
    return message or "Garmin error"


def _is_garmin_auth_error(exc: Exception) -> bool:
    message = str(exc)
    return "Authentication failed" in message or "401 Client Error" in message or "unauthorized" in message.lower()


def _fetch_rows_for_user(user_id: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    try:
        return fetch_training_rows(
            supabase,
            user_id,
            limit=limit if limit is not None else TRAINING_CONFIG.windows.dashboard_history_limit,
        )
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.DB,
            event="training_days.fetch_failed",
            message="Failed to fetch dashboard rows.",
            exc=exc,
            user_id=user_id,
        )
        raise ServiceError(
            "Dashboard data could not be loaded.",
            status_code=500,
            category=ErrorCategory.DB,
            event="training_days.fetch_failed",
            context={"user_id": user_id},
        ) from exc


def _account_summary(user_id: str) -> Dict[str, Any]:
    account = store.fetch_account(user_id)
    return account.ui_summary() if account else {"connected": False}


def _sync_summary(user_id: str) -> Dict[str, Any]:
    return sync_runner.get_status_payload(user_id, include_debug=DEBUG_MODE)


def _render_app_shell():
    return render_template(
        "dashboard.html",
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", ""),
        missing_public_config=_missing_public_config(),
        range_filters=list(TRAINING_CONFIG.windows.range_filters),
        default_range_days=TRAINING_CONFIG.windows.default_dashboard_range,
        debug_mode=DEBUG_MODE,
    )


app.register_blueprint(
    create_dashboard_blueprint(
        fetch_rows=_fetch_rows_for_user,
        account_summary=_account_summary,
        sync_summary=_sync_summary,
        debug_mode=DEBUG_MODE,
    )
)
app.register_blueprint(create_sync_blueprint(sync_runner=sync_runner, debug_mode=DEBUG_MODE))
app.register_blueprint(create_settings_blueprint(account_service=account_service))


def _mark_sync_error(user_id: str, message: str) -> None:
    try:
        store.mark_sync_state(user_id, sync_status="error", sync_error=message)
    except ServiceError as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.DB,
            event="garmin.sync_error_mark_failed",
            message="Failed to record Garmin sync error state.",
            exc=exc,
            user_id=user_id,
            original_error=message,
            level=logging.WARNING,
        )


def _set_sync_status_fields(user_id: str, fields: Dict[str, Any]) -> None:
    try:
        sync_status_service.update_status(user_id, fields)
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.DB,
            event="sync.status_update_failed",
            message="Failed to update sync status fields.",
            exc=exc,
            user_id=user_id,
            level=logging.WARNING,
        )


@app.errorhandler(ServiceError)
def handle_service_error(exc: ServiceError):
    return jsonify({"error": exc.public_message}), exc.status_code


@app.errorhandler(Exception)
def handle_unexpected_error(exc: Exception):
    log_exception(
        LOGGER,
        category=ErrorCategory.API,
        event="unhandled_exception",
        message="Unhandled application exception.",
        exc=exc,
    )
    return jsonify({"error": "internal server error"}), 500


@app.get("/")
def index():
    return _render_app_shell()


@app.get("/auth")
def auth_view():
    return _render_app_shell()


@app.get("/auth/callback")
def auth_callback_view():
    return _render_app_shell()


@app.get("/dashboard")
def dashboard_view():
    return _render_app_shell()


@app.get("/settings")
def settings_view():
    return _render_app_shell()


@app.get("/onboarding/garmin")
def garmin_onboarding_view():
    return _render_app_shell()


@app.get("/api/app-state")
@require_user
def app_state():
    sync_status = _sync_summary(request.user_id)
    account = store.fetch_account(request.user_id)
    return jsonify(build_authenticated_app_state(account, sync_status))


@app.get("/api/history")
@require_user
def api_history():
    rows = _fetch_rows_for_user(request.user_id, limit=90)
    return jsonify({"rows": list(reversed(build_series(rows)))})


@app.get("/api/ai-prompt")
@require_user
def api_ai_prompt():
    mode = mode_or_default(request.args.get("mode", "hybrid"))
    rows = _fetch_rows_for_user(request.user_id)
    selected_date = request.args.get("date")
    latest_payload = payload_for_date(rows, selected_date)
    return jsonify(
        {
            "mode": mode,
            "date": selected_date or (latest_payload or {}).get("date"),
            "prompt": build_prompt_from_payload(latest_payload, mode),
        }
    )


@app.post("/api/garmin/connect")
@require_user
def connect_garmin():
    data = request.get_json(silent=True) or {}
    
    # Validate and sanitize credentials using the new validator
    try:
        email, password = GarminCredentialsValidator.validate(
            data.get("email"),
            data.get("password"),
        )
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError(
            "Invalid credentials format.",
            status_code=400,
            category=ErrorCategory.VALIDATION,
            event="garmin.connect_validation_failed",
        ) from exc

    try:
        garmin_connection_service.connect_account(
            request.user_id,
            email=email,
            password=password,
        )
        status = sync_status_service.ensure_status(request.user_id)
        _set_sync_status_fields(
            request.user_id,
            {
                "sync_state": "never_synced" if not status.get("last_successful_sync_at") else "stale",
                "sync_mode": None,
                "status_reason": "credentials_updated",
                "last_error_category": None,
                "last_error_code": None,
                "last_error_message": None,
                "cooldown_until": None,
                "consecutive_failure_count": 0,
            },
        )
        log_event(
            LOGGER,
            logging.INFO,
            category=ErrorCategory.AUTH,
            event="garmin.connect_success",
            message="Garmin account connected.",
            user_id=request.user_id,
        )
        return jsonify({"status": "connected"})
    except ServiceError:
        raise
    except Exception as exc:
        message = _garmin_error_message(exc)
        _mark_sync_error(request.user_id, message)
        classification = classify_sync_error(exc, consecutive_failure_count=1)
        _set_sync_status_fields(
            request.user_id,
            {
                "sync_state": "blocked" if classification["blocked"] else "error",
                "status_reason": classification["code"],
                "last_error_category": classification["category"],
                "last_error_code": classification["code"],
                "last_error_message": classification["userMessage"],
                "cooldown_until": None,
                "consecutive_failure_count": 1 if classification["retryable"] else 0,
            },
        )
        category = ErrorCategory.AUTH if _is_garmin_auth_error(exc) else ErrorCategory.API
        status_code = 400 if _is_garmin_auth_error(exc) else 500
        log_exception(
            LOGGER,
            category=category,
            event="garmin.connect_failed",
            message="Garmin connect request failed.",
            exc=exc,
            user_id=request.user_id,
        )
        raise ServiceError(
            message,
            status_code=status_code,
            category=category,
            event="garmin.connect_failed",
            context={"user_id": request.user_id},
        ) from exc


if __name__ == "__main__":
    app.run(debug=DEBUG_MODE)
