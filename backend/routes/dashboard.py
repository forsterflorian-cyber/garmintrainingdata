from __future__ import annotations

from typing import Any, Callable, Dict, List

from flask import Blueprint, jsonify, request

from auth_supabase import require_user
from dashboard_service import build_dashboard_payload, mode_or_default
from training_config import TRAINING_CONFIG


def create_dashboard_blueprint(
    *,
    fetch_rows: Callable[..., List[Dict[str, Any]]],
    account_summary: Callable[[str], Dict[str, Any]],
    sync_summary: Callable[[str], Dict[str, Any]] | None = None,
    debug_mode: bool = False,
) -> Blueprint:
    blueprint = Blueprint("dashboard_api", __name__)

    @blueprint.get("/api/dashboard")
    @require_user
    def dashboard():
        period_days = parse_period_days(request.args.get("days"))
        mode = mode_or_default(request.args.get("mode", "hybrid"))
        selected_date = request.args.get("date")
        rows = fetch_rows(
            request.user_id,
            limit=TRAINING_CONFIG.windows.dashboard_history_limit,
        )
        payload = build_dashboard_payload(
            rows,
            account_summary(request.user_id),
            sync_summary=sync_summary(request.user_id) if sync_summary else None,
            selected_date=selected_date,
            mode=mode,
            period_days=period_days,
            include_debug=debug_mode,
        )
        return jsonify(payload)

    return blueprint


def parse_period_days(raw_value: str | None) -> int:
    try:
        days = int(raw_value) if raw_value is not None else TRAINING_CONFIG.windows.default_dashboard_range
    except (TypeError, ValueError):
        days = TRAINING_CONFIG.windows.default_dashboard_range
    return max(1, min(days, TRAINING_CONFIG.windows.dashboard_history_limit))
