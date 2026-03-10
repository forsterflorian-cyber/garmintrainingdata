from __future__ import annotations

from typing import Optional

from flask import Blueprint, jsonify, request

from auth_supabase import require_user
from backend.services.sync_runner import SyncRunner
from dashboard_service import parse_backfill_days
from observability import ErrorCategory, ServiceError


def create_sync_blueprint(
    *,
    sync_runner: SyncRunner,
    debug_mode: bool = False,
) -> Blueprint:
    blueprint = Blueprint("sync_api", __name__)

    def current_status_payload(user_id: str) -> dict:
        return sync_runner.get_status_payload(user_id, include_debug=debug_mode)

    def execute_sync(user_id: str, *, requested_mode: str, trigger_source: str, days: Optional[int] = None):
        decision_context = sync_runner.decide_action(
            user_id,
            trigger_source=trigger_source,
            requested_mode=requested_mode,
        )
        decision = decision_context["decision"]
        if not decision["should_start"]:
            payload = current_status_payload(user_id)
            return jsonify(
                {
                    "started": False,
                    "mode": decision["mode"],
                    "reason": decision["reason"],
                    **payload,
                }
            )

        result = sync_runner.start_sync(
            user_id,
            mode=decision["mode"],
            trigger_source=trigger_source,
            reason=decision["reason"],
            days=days,
        )
        payload = current_status_payload(user_id)
        return jsonify(
            {
                "started": bool(result["started"]),
                "mode": decision["mode"],
                "reason": decision["reason"],
                **payload,
            }
        )

    @blueprint.get("/api/sync/status")
    @require_user
    def sync_status():
        return jsonify(current_status_payload(request.user_id))

    @blueprint.post("/api/sync/auto")
    @require_user
    def sync_auto():
        return execute_sync(request.user_id, requested_mode="auto", trigger_source="auto")

    @blueprint.post("/api/sync/update")
    @require_user
    def sync_update():
        return execute_sync(request.user_id, requested_mode="update", trigger_source="manual_update")

    @blueprint.post("/api/update")
    @require_user
    def sync_update_legacy():
        return execute_sync(request.user_id, requested_mode="update", trigger_source="legacy_update")

    @blueprint.post("/api/sync/backfill")
    @require_user
    def sync_backfill():
        return execute_sync(
            request.user_id,
            requested_mode="backfill",
            trigger_source="manual_backfill",
            days=parse_optional_days(),
        )

    @blueprint.post("/api/backfill")
    @require_user
    def sync_backfill_legacy():
        return execute_sync(
            request.user_id,
            requested_mode="backfill",
            trigger_source="legacy_backfill",
            days=parse_optional_days(),
        )

    @blueprint.post("/api/sync/baseline-rebuild")
    @require_user
    def sync_baseline_rebuild():
        return execute_sync(request.user_id, requested_mode="baseline_rebuild", trigger_source="baseline_rebuild")

    return blueprint


def parse_optional_days() -> Optional[int]:
    raw_value = request.args.get("days")
    if raw_value is None:
        data = request.get_json(silent=True) or {}
        raw_value = data.get("days")
    if raw_value in (None, ""):
        return None
    try:
        return parse_backfill_days(str(raw_value))
    except ValueError as exc:
        raise ServiceError(
            str(exc),
            status_code=400,
            category=ErrorCategory.API,
            event="sync.backfill_invalid_days",
        ) from exc
