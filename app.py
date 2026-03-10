from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request

from auth_supabase import require_user
from dashboard_service import (
    build_dashboard_payload,
    build_prompt_from_payload,
    build_series,
    fetch_training_rows,
    history_from_rows,
    mode_or_default,
    parse_backfill_days,
    payload_for_date,
    upsert_training_payload,
)
from garmin_hybrid_report_v62_supabase_ready import (
    export_client_session,
    get_recent_activities,
    load_client,
    main_logic_for_day,
)
from garmin_session_store import GarminAccount, GarminSessionStore
from observability import ErrorCategory, ServiceError, configure_structured_logging, get_logger, log_event, log_exception
from supabase_client import get_supabase_admin_client
from training_config import TRAINING_CONFIG


supabase = get_supabase_admin_client()
store = GarminSessionStore(supabase)

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _garmin_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if "Authentication failed" in message or "401 Client Error" in message:
        return "Garmin Anmeldung fehlgeschlagen. Bitte Garmin E-Mail und Passwort pruefen."
    return message or "Garmin Fehler"


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
            "Dashboard-Daten konnten nicht geladen werden.",
            status_code=500,
            category=ErrorCategory.DB,
            event="training_days.fetch_failed",
            context={"user_id": user_id},
        ) from exc


def _upsert_user_payload(user_id: str, payload: Dict[str, Any]) -> None:
    try:
        upsert_training_payload(supabase, user_id, payload)
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.DB,
            event="training_days.upsert_failed",
            message="Failed to persist training payload.",
            exc=exc,
            user_id=user_id,
            day=payload.get("date"),
        )
        raise ServiceError(
            "Trainingsdaten konnten nicht gespeichert werden.",
            status_code=500,
            category=ErrorCategory.DB,
            event="training_days.upsert_failed",
            context={"user_id": user_id, "day": payload.get("date")},
        ) from exc


def _account_summary(user_id: str) -> Dict[str, Any]:
    account = store.fetch_account(user_id)
    return account.ui_summary() if account else {"connected": False}


def _get_connected_account(user_id: str) -> GarminAccount:
    account = store.fetch_account(user_id)
    if not account:
        raise ServiceError(
            "garmin not connected",
            status_code=400,
            category=ErrorCategory.AUTH,
            event="garmin.account_missing",
            context={"user_id": user_id},
        )

    if not account.credentials():
        raise ServiceError(
            "garmin not connected",
            status_code=400,
            category=ErrorCategory.AUTH,
            event="garmin.credentials_missing",
            context={"user_id": user_id},
        )

    return account


def _build_authenticated_client(user_id: str) -> tuple[Any, GarminAccount]:
    account = _get_connected_account(user_id)
    email, password = account.credentials() or ("", "")
    session_payload = account.session_payload()

    client = load_client(email=email, password=password, session_data=session_payload)

    refreshed_session = export_client_session(client)
    if refreshed_session:
        try:
            store.save_session_atomically(
                user_id,
                refreshed_session,
                expected_version=account.garmin_session_version,
            )
        except ServiceError as exc:
            if exc.status_code == 409:
                log_event(
                    LOGGER,
                    logging.WARNING,
                    category=ErrorCategory.DB,
                    event="garmin.session_refresh_conflict",
                    message="Garmin session refresh conflicted with a parallel request.",
                    user_id=user_id,
                )
            else:
                raise

    return client, account


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


def _raise_garmin_service_error(user_id: str, exc: Exception, *, event: str, fallback_message: str) -> None:
    is_auth_error = _is_garmin_auth_error(exc)
    message = _garmin_error_message(exc) if is_auth_error else fallback_message
    category = ErrorCategory.AUTH if is_auth_error else ErrorCategory.API
    status_code = 400 if is_auth_error else 500

    log_exception(
        LOGGER,
        category=category,
        event=event,
        message="Garmin sync request failed.",
        exc=exc,
        user_id=user_id,
        auth_error=is_auth_error,
    )
    _mark_sync_error(user_id, _garmin_error_message(exc))

    if is_auth_error:
        try:
            store.clear_session(user_id)
        except ServiceError as clear_exc:
            log_exception(
                LOGGER,
                category=ErrorCategory.DB,
                event="garmin.session_clear_failed",
                message="Failed to clear stale Garmin session after auth error.",
                exc=clear_exc,
                user_id=user_id,
                level=logging.WARNING,
            )

    raise ServiceError(
        message,
        status_code=status_code,
        category=category,
        event=event,
        context={"user_id": user_id},
    ) from exc


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
    return render_template(
        "dashboard.html",
        supabase_url=os.environ.get("SUPABASE_URL", ""),
        supabase_anon_key=os.environ.get("SUPABASE_ANON_KEY", ""),
        missing_public_config=_missing_public_config(),
        range_filters=list(TRAINING_CONFIG.windows.range_filters),
        default_range_days=TRAINING_CONFIG.windows.default_dashboard_range,
    )


@app.get("/api/history")
@require_user
def api_history():
    rows = _fetch_rows_for_user(request.user_id, limit=90)
    return jsonify({"rows": list(reversed(build_series(rows)))})


@app.get("/api/dashboard")
@require_user
def dashboard():
    rows = _fetch_rows_for_user(request.user_id)
    payload = build_dashboard_payload(rows, _account_summary(request.user_id))
    return jsonify(payload)


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


@app.post("/api/update")
@require_user
def update():
    try:
        client, _account = _build_authenticated_client(request.user_id)
        rows = _fetch_rows_for_user(request.user_id)
        history = history_from_rows(rows)
        recent_activities = get_recent_activities(client, TRAINING_CONFIG.windows.default_activity_limit)

        today = date.today().isoformat()
        payload = main_logic_for_day(
            day=today,
            mode="hybrid",
            history=history,
            client=client,
            recent_activities=recent_activities,
            persist_history=False,
        )

        _upsert_user_payload(request.user_id, payload)
        store.mark_sync_state(
            request.user_id,
            sync_status="ok",
            sync_error=None,
            last_sync_at=_now_iso(),
        )
        return jsonify({"status": "ok", "date": payload["date"]})
    except ServiceError:
        raise
    except Exception as exc:
        _raise_garmin_service_error(
            request.user_id,
            exc,
            event="garmin.update_failed",
            fallback_message="update failed",
        )


@app.post("/api/backfill")
@require_user
def backfill_data():
    try:
        days = parse_backfill_days(request.args.get("days", str(TRAINING_CONFIG.windows.chronic_load_days)))
    except ValueError as exc:
        raise ServiceError(
            str(exc),
            status_code=400,
            category=ErrorCategory.API,
            event="garmin.backfill_invalid_days",
        ) from exc

    try:
        client, _account = _build_authenticated_client(request.user_id)
        rows = _fetch_rows_for_user(request.user_id)
        history = history_from_rows(rows)
        recent_activities = get_recent_activities(client, TRAINING_CONFIG.windows.default_activity_limit)

        results: List[str] = []
        for offset in range(days - 1, -1, -1):
            day = (date.today() - timedelta(days=offset)).isoformat()
            payload = main_logic_for_day(
                day=day,
                mode="hybrid",
                history=history,
                client=client,
                recent_activities=recent_activities,
                persist_history=False,
            )
            _upsert_user_payload(request.user_id, payload)
            history["days"][day] = {
                "morning": payload.get("morning"),
                "summary": payload.get("summary") or {},
            }
            results.append(day)

        store.mark_sync_state(
            request.user_id,
            sync_status="ok",
            sync_error=None,
            last_sync_at=_now_iso(),
        )
        return jsonify({"status": "backfilled", "days": len(results), "dates": results})
    except ServiceError:
        raise
    except Exception as exc:
        _raise_garmin_service_error(
            request.user_id,
            exc,
            event="garmin.backfill_failed",
            fallback_message="backfill failed",
        )


@app.post("/api/garmin/connect")
@require_user
def connect_garmin():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")

    if not isinstance(email, str) or not isinstance(password, str):
        raise ServiceError(
            "email and password are required",
            status_code=400,
            category=ErrorCategory.AUTH,
            event="garmin.connect_missing_fields",
        )

    email = email.strip()
    password = password.strip()
    if not email or not password:
        raise ServiceError(
            "email and password are required",
            status_code=400,
            category=ErrorCategory.AUTH,
            event="garmin.connect_empty_fields",
        )

    try:
        client = load_client(email=email, password=password)
        session_payload = export_client_session(client)
        if not session_payload:
            raise ServiceError(
                "Garmin session could not be serialized.",
                status_code=500,
                category=ErrorCategory.API,
                event="garmin.connect_session_missing",
            )

        store.save_connected_account(request.user_id, email, password, session_payload)
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
    app.run(debug=True)
