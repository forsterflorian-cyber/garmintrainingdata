from __future__ import annotations

from typing import Any, Dict, List, Optional

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
        payload = row.get("data") or {}
        day = payload.get("date") or row.get("date")
        if not day:
            continue
        history["days"][day] = {
            "morning": payload.get("morning"),
            "summary": payload.get("summary") or {},
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


def payload_to_series_item(payload: Dict[str, Any]) -> Dict[str, Any]:
    morning = payload.get("morning") or {}
    load_metrics = payload.get("load_metrics") or {}
    recs = payload.get("recommendations") or {}
    units = payload.get("units") or {}
    summary = payload.get("summary") or {}
    readiness = payload.get("readiness") or {}
    relative_metrics = build_relative_metrics(morning, readiness)

    return {
        "date": payload.get("date"),
        "readiness": readiness.get("score"),
        "readiness_reason": readiness.get("reason"),
        "readiness_bands": readiness.get("bands") or {},
        "load_day": summary.get("training_load_sum", 0),
        "load_7d": load_metrics.get("load_7d"),
        "load_28d": load_metrics.get("load_28d"),
        "ratio": load_metrics.get("load_ratio"),
        "ratio_label": load_metrics.get("load_ratio_label"),
        "resting_hr": morning.get("resting_hr"),
        "hrv": morning.get("hrv"),
        "respiration": morning.get("respiration"),
        "sleep_h": morning.get("sleep_h"),
        "spo2": morning.get("pulse_ox"),
        "recommendation_hybrid": recs.get("hybrid"),
        "recommendation_run": recs.get("run"),
        "recommendation_bike": recs.get("bike"),
        "recommendation_strength": recs.get("strength"),
        "units_hybrid": units.get("hybrid", []),
        "units_run": units.get("run", []),
        "units_bike": units.get("bike", []),
        "units_strength": units.get("strength", []),
        "activities": payload.get("activities", []),
        "recommendation_day": payload.get("recommendation_day"),
        "ai_prompt": payload.get("ai_prompt"),
        "relative_metrics": relative_metrics,
        "stress_label": stress_label(summary),
    }


def build_series(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in rows:
        payload = row.get("data") or {}
        if payload.get("date"):
            items.append(payload_to_series_item(payload))
    items.sort(key=lambda item: item["date"])
    return items


def payload_for_date(rows: List[Dict[str, Any]], selected_date: Optional[str]) -> Optional[Dict[str, Any]]:
    if selected_date:
        for row in rows:
            payload = row.get("data") or {}
            row_date = payload.get("date") or row.get("date")
            if row_date == selected_date:
                return payload
    return rows[-1].get("data") if rows else None


def build_prompt_from_payload(payload: Optional[Dict[str, Any]], mode: str) -> str:
    if not payload:
        return "Keine Daten verfuegbar."

    mode = mode_or_default(mode)
    recommendation_day = payload.get("recommendation_day") or payload.get("date")
    morning = payload.get("morning")
    summary = payload.get("summary") or {}
    load_metrics = payload.get("load_metrics") or {}
    activities = [ActivitySummary(**activity) for activity in (payload.get("activities") or [])]
    recommendations = payload.get("recommendations") or {}
    units = (payload.get("units") or {}).get(mode) or (payload.get("units") or {}).get("hybrid", [])

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


def build_dashboard_payload(rows: List[Dict[str, Any]], account_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    series = build_series(rows)
    latest = series[-1] if series else None
    load_values = [item.get("load_day") or 0 for item in series]
    readiness_values = [item.get("readiness") for item in series if isinstance(item.get("readiness"), int)]

    return {
        "latest": latest,
        "series": series,
        "account": account_summary or {},
        "ranges": list(TRAINING_CONFIG.windows.range_filters),
        "default_range_days": TRAINING_CONFIG.windows.default_dashboard_range,
        "summary": {
            "avg_load": round(sum(load_values) / len(load_values), 1) if load_values else None,
            "avg_readiness": round(sum(readiness_values) / len(readiness_values), 1) if readiness_values else None,
            "days": len(series),
        },
    }


def build_relative_metrics(morning: Dict[str, Any], readiness: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    baselines = readiness.get("baselines") or {}
    bands = readiness.get("bands") or {}
    metrics: Dict[str, Dict[str, Any]] = {}

    for key, higher_is_better in TRAINING_CONFIG.readiness.higher_is_better.items():
        current = morning.get(key)
        baseline_payload = baselines.get(key) or {}
        baseline = baseline_payload.get("baseline")
        std = baseline_payload.get("std")
        n = baseline_payload.get("n")
        metrics[key] = relative_metric_view(
            metric_key=key,
            current=current,
            baseline=baseline,
            std=std,
            n=n,
            band=bands.get(key),
            higher_is_better=higher_is_better,
        )

    return metrics


def relative_metric_view(
    *,
    metric_key: str,
    current: Optional[float],
    baseline: Optional[float],
    std: Optional[float],
    n: Optional[int],
    band: Optional[str],
    higher_is_better: bool,
) -> Dict[str, Any]:
    label = TRAINING_CONFIG.metric_labels.get(metric_key, metric_key)
    if current is None or baseline is None:
        return {
            "label": label,
            "current": current,
            "baseline": baseline,
            "delta": None,
            "delta_pct": None,
            "z_score": None,
            "n": n,
            "band": band or "-",
            "state": "unknown",
            "progress": 0,
        }

    std_effective = max(float(std or 0.0), TRAINING_CONFIG.readiness.std_floor)
    delta = float(current) - float(baseline)
    direction = delta if higher_is_better else -delta
    z_score = direction / std_effective
    clipped = max(-TRAINING_CONFIG.readiness.z_clip, min(TRAINING_CONFIG.readiness.z_clip, z_score))
    progress = round(((clipped + TRAINING_CONFIG.readiness.z_clip) / (2 * TRAINING_CONFIG.readiness.z_clip)) * 100)

    if clipped >= 0.5:
        state = "positive"
    elif clipped >= -1.0:
        state = "warning"
    else:
        state = "critical"

    delta_pct = None
    if baseline not in (None, 0):
        delta_pct = round((delta / float(baseline)) * 100, 1)

    return {
        "label": label,
        "current": current,
        "baseline": baseline,
        "delta": round(delta, 2),
        "delta_pct": delta_pct,
        "z_score": round(z_score, 2),
        "n": n,
        "band": band or "-",
        "state": state,
        "progress": max(0, min(100, progress)),
    }


def stress_label(day: Dict[str, Optional[float]]) -> str:
    aero = day.get("aero_te_sum") or 0
    anaer = day.get("anaer_te_sum") or 0
    load = day.get("training_load_sum") or 0
    cfg = TRAINING_CONFIG.stress
    if aero >= cfg.high_aero_te or anaer >= cfg.high_anaerobic_te or load >= cfg.high_load:
        return "high"
    if aero >= cfg.moderate_aero_te or anaer >= cfg.moderate_anaerobic_te or load >= cfg.moderate_load:
        return "moderate"
    return "low"
