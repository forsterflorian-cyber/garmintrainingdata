from __future__ import annotations

from typing import Any, Callable, Dict, List

from flask import Blueprint, jsonify, request
from datetime import datetime, timezone
from supabase_client import get_supabase_admin_client
from auth_supabase import require_user
from dashboard_service import build_dashboard_payload, mode_or_default
from training_config import TRAINING_CONFIG

ALLOWED_JUDGEMENTS = {
    "correct",
    "too_conservative",
    "too_aggressive",
    "insufficient_data",
}

ALLOWED_RECOMMENDATIONS = {
    "recovery",
    "easy",
    "moderate",
    "threshold",
    "vo2",
    "strength_light",
    "strength_hypertrophy",
    "rest",
}

ALLOWED_PROBLEM_AREAS = {
    "recovery_thresholds",
    "load_tolerance",
    "intensity_gate",
    "strength_handling",
    "none",
    "unknown",
}

ALLOWED_CONFIDENCE = {
    "low",
    "medium",
    "high",
}


def _validate_review_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("review payload must be an object")

    if payload.get("judgement") not in ALLOWED_JUDGEMENTS:
        raise ValueError("invalid judgement")

    if payload.get("recommendedSession") not in ALLOWED_RECOMMENDATIONS:
        raise ValueError("invalid recommendedSession")

    if payload.get("suspectedProblemArea") not in ALLOWED_PROBLEM_AREAS:
        raise ValueError("invalid suspectedProblemArea")

    if payload.get("confidence") not in ALLOWED_CONFIDENCE:
        raise ValueError("invalid confidence")

    agreement = payload.get("agreementWithRuleModel")
    if not isinstance(agreement, bool):
        raise ValueError("agreementWithRuleModel must be boolean")

    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, list) or not all(isinstance(item, str) for item in reasoning):
        raise ValueError("reasoning must be a list of strings")

    tuning_hint = payload.get("tuningHint")
    if tuning_hint is not None and not isinstance(tuning_hint, str):
        raise ValueError("tuningHint must be a string")

    return payload

def _fetch_review_status(user_id: str, review_date: str | None, mode: str) -> Dict[str, Any] | None:
    if not review_date:
        return None

    supabase = get_supabase_admin_client()
    result = (
        supabase.table("training_case_reviews")
        .select("review_payload, updated_at")
        .eq("user_id", user_id)
        .eq("review_date", review_date)
        .eq("mode", mode)
        .limit(1)
        .execute()
    )

    rows = result.data or []
    if not rows:
        return None

    row = rows[0]
    review = row.get("review_payload") or {}

    return {
        "reviewed": True,
        "judgement": review.get("judgement"),
        "problemArea": review.get("suspectedProblemArea"),
        "recommendedSession": review.get("recommendedSession"),
        "confidence": review.get("confidence"),
        "updatedAt": row.get("updated_at"),
    }

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
        review_status = _fetch_review_status(
            request.user_id,
            payload.get("date"),
            mode,
        )

        payload["reviewStatus"] = review_status or {
            "reviewed": False,
            "judgement": None,
            "problemArea": None,
            "recommendedSession": None,
            "confidence": None,
            "updatedAt": None,
        }
        return jsonify(payload)

    @blueprint.post("/api/dashboard/reviews")
    @require_user
    def save_dashboard_review():
        body = request.get_json(silent=True) or {}
        case = body.get("case")
        review = body.get("review")

        if not isinstance(case, dict):
            return jsonify({"error": "missing case"}), 400

        try:
            review = _validate_review_payload(review)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        review_date = case.get("date")
        mode = case.get("mode")

        if not review_date or not isinstance(review_date, str):
            return jsonify({"error": "invalid case date"}), 400

        if not mode or not isinstance(mode, str):
            return jsonify({"error": "invalid case mode"}), 400

        supabase = get_supabase_admin_client()
        now = datetime.now(timezone.utc).isoformat()

        row = {
            "user_id": request.user_id,
            "review_date": review_date,
            "mode": mode,
            "case_payload": case,
            "review_payload": review,
            "created_at": now,
            "updated_at": now,
        }

        (
            supabase.table("training_case_reviews")
            .upsert(row, on_conflict="user_id,review_date,mode")
            .execute()
        )

        return jsonify({"ok": True})

    return blueprint


def parse_period_days(raw_value: str | None) -> int:
    try:
        days = int(raw_value) if raw_value is not None else TRAINING_CONFIG.windows.default_dashboard_range
    except (TypeError, ValueError):
        days = TRAINING_CONFIG.windows.default_dashboard_range
    return max(1, min(days, TRAINING_CONFIG.windows.dashboard_history_limit))
