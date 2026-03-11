from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.services.baseline_service import (
    build_baseline_metrics_snapshot,
    build_comparisons,
    build_metric_delta_bars,
    build_today_metrics,
)
from backend.services.load_service import build_load_snapshot, classify_day_intensity
from backend.services.training_decision import compute_training_decision
from garmin_hybrid_report_v62_supabase_ready import ActivitySummary, build_ai_prompt as report_build_ai_prompt
from training_config import TRAINING_CONFIG


VALID_MODES = {"hybrid", "run", "bike", "strength"}


def mode_or_default(value: Optional[str]) -> str:
    return value if value in VALID_MODES else "hybrid"


def fetch_training_rows(supabase: Any, user_id: str, *, limit: int = 0) -> List[Dict[str, Any]]:
    query = (
        supabase.table("training_days")
        .select("user_id,date,data")
        .eq("user_id", user_id)
        .order("date", desc=True)
    )
    if limit > 0:
        query = query.limit(limit)

    response = query.execute()
    rows = response.data or []
    rows.sort(key=lambda row: row.get("date") or "")
    return rows


def history_from_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    history: Dict[str, Any] = {"days": {}}
    for row in rows:
        payload = _normalized_row_payload(row)
        if not payload:
            continue
        history["days"][payload["date"]] = {
            "morning": _dict_or_none(payload.get("morning")),
            "summary": _dict_or_empty(payload.get("summary")),
        }
    return history


def upsert_training_payload(supabase: Any, user_id: str, payload: Dict[str, Any]) -> None:
    (
        supabase.table("training_days")
        .upsert(
            {
                "user_id": user_id,
                "date": payload["date"],
                "data": payload,
            },
            on_conflict="user_id,date",
        )
        .execute()
    )


def payload_for_date(rows: List[Dict[str, Any]], selected_date: Optional[str]) -> Optional[Dict[str, Any]]:
    latest_payload: Optional[Dict[str, Any]] = None
    if selected_date:
        for row in rows:
            payload = _normalized_row_payload(row)
            if not payload:
                continue
            latest_payload = payload
            if payload["date"] == selected_date:
                return payload
        return latest_payload

    for row in rows:
        payload = _normalized_row_payload(row)
        if payload:
            latest_payload = payload
    return latest_payload


def build_series(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = build_day_items(rows, mode="hybrid")
    return [
        {
            "date": item["date"],
            "recommendation_day": item["recommendationDay"],
            "readiness": item["today"].get("readiness"),
            "load_day": item.get("loadDay"),
            "load_7d": item.get("acute7d"),
            "load_28d": item.get("chronic28d"),
            "ratio": item.get("ratio7to28"),
            "ratio_label": item.get("ratioLabel"),
            "recommendation_hybrid": item["decision"]["primaryRecommendation"],
            "recommendation_run": item["decision"]["primaryRecommendation"],
            "recommendation_bike": item["decision"]["primaryRecommendation"],
            "recommendation_strength": item["decision"]["primaryRecommendation"],
            "activities": item["activities"],
            "units_hybrid": (item["legacyUnits"] or {}).get("hybrid", []),
            "units_run": (item["legacyUnits"] or {}).get("run", []),
            "units_bike": (item["legacyUnits"] or {}).get("bike", []),
            "units_strength": (item["legacyUnits"] or {}).get("strength", []),
            "ai_prompt": item["aiPrompt"],
        }
        for item in items
    ]


def build_prompt_from_payload(payload: Optional[Dict[str, Any]], mode: str) -> str:
    if not isinstance(payload, dict) or not payload:
        return "No Data Available."

    mode = mode_or_default(mode)
    recommendation_day = payload.get("recommendation_day") or payload.get("date")
    morning = _dict_or_none(payload.get("morning"))
    summary = _dict_or_empty(payload.get("summary"))
    load_metrics = _dict_or_empty(payload.get("load_metrics"))
    activities = [_activity_summary(activity) for activity in _sanitized_activities(payload.get("activities"))]
    recommendations = _dict_or_empty(payload.get("recommendations"))
    units_payload = _dict_or_empty(payload.get("units"))
    units = units_payload.get(mode) or units_payload.get("hybrid", [])

    return report_build_ai_prompt(
        mode=mode,
        recommendation_day=recommendation_day,
        today_day=payload.get("date"),
        latest_morning=None if not morning else type("MorningProxy", (), morning)(),
        today_summary=summary,
        today_load_metrics=load_metrics,
        today_activities=activities,
        dashboard_recommendations=recommendations,
        units=units,
    )


def parse_backfill_days(raw_value: str) -> int:
    try:
        days = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("days must be an integer") from exc
    return max(1, min(days, 180))


def build_dashboard_payload(
    rows: List[Dict[str, Any]],
    account_summary: Optional[Dict[str, Any]] = None,
    sync_summary: Optional[Dict[str, Any]] = None,
    *,
    selected_date: Optional[str] = None,
    mode: str = "hybrid",
    period_days: int = TRAINING_CONFIG.windows.default_dashboard_range,
    include_debug: bool = False,
) -> Dict[str, Any]:
    mode = mode_or_default(mode)
    day_items = build_day_items(rows, mode=mode)
    if not day_items:
        return {
            "date": selected_date,
            "mode": mode,
            "filters": {"periodDays": period_days},
            "account": account_summary or {},
            "sync": sync_summary or {},
            "history": {"rows": []},
            "trends": {"readinessSeries": [], "loadSeries": []},
            "summary": {"avgReadiness": None, "avgLoad": None, "days": 0},
        }

    focus_item = select_focus_item(day_items, selected_date)
    filtered_items = filter_period_items(day_items, focus_item["date"], period_days)
    summary = build_summary(filtered_items)

    payload = {
        "date": focus_item["date"],
        "mode": mode,
        "filters": {"periodDays": period_days},
        "today": {
            **focus_item["today"],
            "pulseOx": focus_item.get("pulseOx"),
            "recommendationDay": focus_item["recommendationDay"],
            "activities": focus_item["activities"],
            "sessionType": focus_item.get("sessionType"),
        },
        "baseline": focus_item["baseline"],
        "load": focus_item["load"],
        "decision": focus_item["decision"],
        "comparisons": focus_item["comparisons"],
        "baselineBars": focus_item["baselineBars"],
        "trends": {
            "readinessSeries": [
                {"date": item["date"], "value": item["today"].get("readiness")}
                for item in filtered_items
            ],
            "loadSeries": [
                {
                    "date": item["date"],
                    "loadDay": item.get("loadDay"),
                    "acute7d": item.get("acute7d"),
                    "chronic28d": item.get("chronic28d"),
                    "ratio7to28": item.get("ratio7to28"),
                    "primaryRecommendation": item["decision"]["primaryRecommendation"],
                }
                for item in filtered_items
            ],
        },
        "history": {
            "rows": [
                {
                    "date": item["date"],
                    "recommendationDay": item["recommendationDay"],
                    "readiness": item["today"].get("readiness"),
                    "loadDay": item.get("loadDay"),
                    "ratio7to28": item.get("ratio7to28"),
                    "primaryRecommendation": item["decision"]["primaryRecommendation"],
                    "sessionType": item.get("sessionType"),
                    "decision": item["decision"],
                    "activities": item["activities"],
                    "legacyRecommendations": item["legacyRecommendations"],
                    "legacyUnits": item["legacyUnits"],
                    "aiPrompt": item["aiPrompt"],
                }
                for item in filtered_items
            ]
        },
        "account": account_summary or {},
        "sync": sync_summary or {},
        "summary": summary,
        "detail": {
            "activeDate": focus_item["date"],
            "sessionType": focus_item.get("sessionType"),
            "activities": focus_item["activities"],
            "legacyRecommendations": focus_item["legacyRecommendations"],
            "legacyUnits": focus_item["legacyUnits"],
            "aiPrompt": focus_item["aiPrompt"],
        },
    }
    if include_debug:
        payload["debug"] = focus_item["decision"].get("debug")
    return payload


def build_day_items(rows: List[Dict[str, Any]], *, mode: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        payload = _normalized_row_payload(row)
        if not payload:
            continue
        item = payload_to_day_item(payload, mode=mode)
        item["sessionType"] = classify_day_intensity(item)
        items.append(item)

    items.sort(key=lambda item: item["date"])

    for item in items:
        load_snapshot = build_load_snapshot(item, items)
        decision_input = {
            "date": item["date"],
            "mode": mode,
            "today": item["today"],
            "baseline": item["baseline"],
            "load": load_snapshot,
            "comparisons": item["comparisons"],
        }
        item["load"] = load_snapshot
        item["decision"] = compute_training_decision(decision_input)

    return items


def payload_to_day_item(payload: Dict[str, Any], *, mode: str) -> Dict[str, Any]:
    morning = _dict_or_empty(payload.get("morning"))
    summary = _dict_or_empty(payload.get("summary"))
    load_metrics = _dict_or_empty(payload.get("load_metrics"))
    readiness = _dict_or_empty(payload.get("readiness"))
    today = build_today_metrics(morning, readiness.get("score"))
    baseline = build_baseline_metrics_snapshot(readiness)
    comparisons = build_comparisons(today, baseline)
    activities = _sanitized_activities(payload.get("activities"))
    legacy_recommendations = _dict_or_empty(payload.get("recommendations"))
    legacy_units = _dict_or_empty(payload.get("units"))

    return {
        "date": payload.get("date"),
        "mode": mode,
        "today": today,
        "pulseOx": morning.get("pulse_ox"),
        "baseline": baseline,
        "comparisons": comparisons,
        "baselineBars": build_metric_delta_bars(today, baseline),
        "recommendationDay": payload.get("recommendation_day") or payload.get("date"),
        "activities": activities,
        "legacyRecommendations": legacy_recommendations,
        "legacyUnits": legacy_units,
        "aiPrompt": payload.get("ai_prompt") if isinstance(payload.get("ai_prompt"), str) else None,
        "loadDay": _safe_number(summary.get("training_load_sum")) or 0.0,
        "acute7d": _safe_number(load_metrics.get("load_7d")),
        "chronic28d": _safe_number(load_metrics.get("load_28d")),
        "acute7dDailyAvg": _safe_number(load_metrics.get("load_7d_daily_avg")),
        "chronic28dDailyAvg": _safe_number(load_metrics.get("load_28d_daily_avg")),
        "ratio7to28": _safe_number(load_metrics.get("load_ratio")),
        "ratioLabel": load_metrics.get("load_ratio_label"),
        "aeroTeSum": _safe_number(summary.get("aero_te_sum")),
        "anaerTeSum": _safe_number(summary.get("anaer_te_sum")),
    }


def select_focus_item(day_items: List[Dict[str, Any]], selected_date: Optional[str]) -> Dict[str, Any]:
    if selected_date:
        for item in day_items:
            if item["date"] == selected_date:
                return item
    return day_items[-1]


def filter_period_items(day_items: List[Dict[str, Any]], focus_date: str, period_days: int) -> List[Dict[str, Any]]:
    return [
        item
        for item in day_items
        if (distance := _date_distance(item["date"], focus_date)) is not None and distance < period_days
    ]


def build_summary(day_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    readiness_values = [item["today"].get("readiness") for item in day_items if isinstance(item["today"].get("readiness"), (int, float))]
    load_values = [item.get("loadDay") or 0.0 for item in day_items]
    return {
        "avgReadiness": round(sum(readiness_values) / len(readiness_values), 1) if readiness_values else None,
        "avgLoad": round(sum(load_values) / len(load_values), 1) if load_values else None,
        "days": len(day_items),
    }


def _date_distance(day: str, focus_day: str) -> Optional[int]:
    day_value = _parse_iso_day(day)
    focus_value = _parse_iso_day(focus_day)
    if day_value is None or focus_value is None:
        return None
    return abs((focus_value - day_value).days)


def _safe_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            number = float(stripped)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return number


def _dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_or_none(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def _normalized_row_payload(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    payload = row.get("data")
    if not isinstance(payload, dict):
        return None
    normalized_date = _normalized_iso_day(payload.get("date") or row.get("date"))
    if normalized_date is None:
        return None
    return {**payload, "date": normalized_date}


def _sanitized_activities(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    activities: List[Dict[str, Any]] = []
    for item in value:
        activity = _sanitized_activity(item)
        if activity is not None:
            activities.append(activity)
    return activities


def _sanitized_activity(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None

    type_key = _string_or_default(value.get("type_key"), "unknown")
    name = _string_or_default(value.get("name"), type_key)
    return {
        "activity_id": _safe_int(value.get("activity_id")),
        "start_local": _string_or_default(value.get("start_local"), ""),
        "date_local": _string_or_default(value.get("date_local"), ""),
        "type_key": type_key,
        "name": name,
        "duration_min": _safe_number(value.get("duration_min")),
        "distance_km": _safe_number(value.get("distance_km")),
        "avg_hr": _safe_number(value.get("avg_hr")),
        "max_hr": _safe_number(value.get("max_hr")),
        "avg_power": _safe_number(value.get("avg_power")),
        "max_power": _safe_number(value.get("max_power")),
        "avg_speed_kmh": _safe_number(value.get("avg_speed_kmh")),
        "pace_min_per_km": _string_or_none(value.get("pace_min_per_km")),
        "aerobic_te": _safe_number(value.get("aerobic_te")),
        "anaerobic_te": _safe_number(value.get("anaerobic_te")),
        "training_load": _safe_number(value.get("training_load")),
    }


def _activity_summary(activity: Dict[str, Any]) -> ActivitySummary:
    return ActivitySummary(
        activity_id=activity.get("activity_id"),
        start_local=activity["start_local"],
        date_local=activity["date_local"],
        type_key=activity["type_key"],
        name=activity["name"],
        duration_min=activity.get("duration_min"),
        distance_km=activity.get("distance_km"),
        avg_hr=activity.get("avg_hr"),
        max_hr=activity.get("max_hr"),
        avg_power=activity.get("avg_power"),
        max_power=activity.get("max_power"),
        avg_speed_kmh=activity.get("avg_speed_kmh"),
        pace_min_per_km=activity.get("pace_min_per_km"),
        aerobic_te=activity.get("aerobic_te"),
        anaerobic_te=activity.get("anaerobic_te"),
        training_load=activity.get("training_load"),
    )


def _normalized_iso_day(value: Any) -> Optional[str]:
    parsed = _parse_iso_day(value)
    return parsed.isoformat() if parsed is not None else None


def _parse_iso_day(value: Any):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _string_or_default(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value
    return default


def _string_or_none(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    return None
