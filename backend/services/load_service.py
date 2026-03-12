from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional


QUALITY_DAY_TYPES = {"threshold", "vo2"}
LOAD_MOMENTUM_STABLE_BAND = 0.10


def classify_day_intensity(day_item: Dict[str, Any]) -> str:
    activities = day_item.get("activities") or []
    load_day = float(day_item.get("loadDay") or 0.0)
    aero_sum = float(day_item.get("aeroTeSum") or 0.0)
    anaer_sum = float(day_item.get("anaerTeSum") or 0.0)
    strength_only_day = bool(activities) and all(_activity_sport_tag(activity) == "strength" for activity in activities)

    if strength_only_day:
        if any(_is_heavy_strength_activity(activity) for activity in activities) or load_day >= 50.0:
            return "heavy_strength"
        return "light_strength"

    if any(_is_vo2_activity(activity) for activity in activities) or aero_sum >= 4.5 or anaer_sum >= 1.8 or load_day >= 120:
        return "vo2"
    if any(_is_threshold_activity(activity) for activity in activities) or aero_sum >= 3.0 or anaer_sum >= 0.8 or load_day >= 75:
        return "threshold"
    if load_day >= 40:
        return "moderate"
    if load_day > 0:
        return "easy"
    return "recovery"


def classify_activity_intensity(activity: Dict[str, Any]) -> str:
    if not isinstance(activity, dict):
        return "recovery"

    if _activity_sport_tag(activity) == "strength":
        if _is_heavy_strength_activity(activity):
            return "heavy_strength"
        return "light_strength"
    if _is_vo2_activity(activity):
        return "vo2"
    if _is_threshold_activity(activity):
        return "threshold"

    load_value = _safe_number(activity.get("training_load")) or 0.0
    if load_value >= 40.0:
        return "moderate"
    if load_value > 0.0:
        return "easy"
    return "recovery"


def build_load_snapshot(focus_item: Dict[str, Any], day_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    focus_date = focus_item["date"]
    yesterday = previous_day_item(focus_item, day_items)
    hard_sessions_last_3d = count_quality_days(focus_date, day_items, days=3)
    hard_sessions_last_7d = count_quality_days(focus_date, day_items, days=7)
    ratio = _safe_number(focus_item.get("ratio7to28"))
    current_7d_load = _safe_number(focus_item.get("acute7d"))
    if current_7d_load is None:
        current_7d_load = sum_window_load(focus_date, day_items, start_offset=0, end_offset=7)
    previous_7d_load = sum_window_load(focus_date, day_items, start_offset=7, end_offset=14)
    chronic_daily_avg = _safe_number(focus_item.get("chronic28dDailyAvg"))
    yesterday_load = _safe_number(yesterday.get("loadDay")) if yesterday else None
    yesterday_session_type = yesterday.get("sessionType") if yesterday else None
    very_high_yesterday_load = bool(
        yesterday_load is not None and yesterday_load >= max(70.0, float(chronic_daily_avg or 0.0) * 1.5)
    )

    return {
        "acute7d": _safe_number(focus_item.get("acute7d")),
        "chronic28d": _safe_number(focus_item.get("chronic28d")),
        "ratio7to28": ratio,
        "yesterdayLoad": yesterday_load,
        "hardSessionsLast3d": hard_sessions_last_3d,
        "hardSessionsLast7d": hard_sessions_last_7d,
        "yesterdaySessionType": yesterday_session_type,
        "veryHighYesterdayLoad": very_high_yesterday_load,
        "momentum": compute_load_momentum(current_7d_load=current_7d_load, previous_7d_load=previous_7d_load),
    }


def compute_load_momentum(*, current_7d_load: Optional[float], previous_7d_load: Optional[float]) -> Dict[str, Any]:
    current_value = _safe_number(current_7d_load)
    previous_value = _safe_number(previous_7d_load)
    if current_value is None or previous_value in (None, 0.0):
        return {
            "value": None,
            "label": None,
            "current7dLoad": current_value,
            "previous7dLoad": previous_value,
        }

    momentum = round((current_value - previous_value) / previous_value, 3)
    return {
        "value": momentum,
        "label": load_momentum_label(momentum),
        "current7dLoad": current_value,
        "previous7dLoad": previous_value,
    }


def load_momentum_label(momentum: Optional[float]) -> Optional[str]:
    value = _safe_number(momentum)
    if value is None:
        return None
    if value > LOAD_MOMENTUM_STABLE_BAND:
        return "Rising"
    if value < -LOAD_MOMENTUM_STABLE_BAND:
        return "Falling"
    return "Stable"


def sum_window_load(
    focus_date: str,
    day_items: List[Dict[str, Any]],
    *,
    start_offset: int,
    end_offset: int,
) -> Optional[float]:
    expected_days = end_offset - start_offset
    if expected_days <= 0:
        return None

    observed_offsets = set()
    total_load = 0.0

    for item in day_items:
        date_value = item.get("date")
        if not isinstance(date_value, str):
            continue
        distance = _date_distance(date_value, focus_date)
        if distance is None or distance < start_offset or distance >= end_offset:
            continue

        load_value = _safe_number(item.get("loadDayRaw"))
        if load_value is None:
            return None

        observed_offsets.add(distance)
        total_load += load_value

    if len(observed_offsets) != expected_days:
        return None
    return round(total_load, 1)


def count_quality_days(focus_date: str, day_items: List[Dict[str, Any]], *, days: int) -> int:
    total = 0
    for item in day_items:
        date_value = item.get("date")
        if not isinstance(date_value, str) or date_value >= focus_date:
            continue
        distance = _date_distance(date_value, focus_date)
        if distance is None or distance > days:
            continue
        if item.get("sessionType") in QUALITY_DAY_TYPES:
            total += 1
    return total


def previous_day_item(focus_item: Dict[str, Any], day_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    focus_date = focus_item["date"]
    previous_items: List[Dict[str, Any]] = []
    for item in day_items:
        date_value = item.get("date")
        if not isinstance(date_value, str) or date_value >= focus_date:
            continue
        if _date_distance(date_value, focus_date) == 1:
            previous_items.append(item)
    if not previous_items:
        return None
    previous_items.sort(key=lambda item: item["date"])
    return previous_items[-1]


def _date_distance(day: str, focus_day: str) -> Optional[int]:
    day_value = _parse_iso_day(day)
    focus_value = _parse_iso_day(focus_day)
    if day_value is None or focus_value is None:
        return None
    return (focus_value - day_value).days


def _is_threshold_activity(activity: Dict[str, Any]) -> bool:
    if not isinstance(activity, dict):
        return False
    return (
        (_safe_number(activity.get("aerobic_te")) or 0.0) >= 2.8
        or (_safe_number(activity.get("anaerobic_te")) or 0.0) >= 0.7
        or (_safe_number(activity.get("training_load")) or 0.0) >= 70.0
    )


def _is_vo2_activity(activity: Dict[str, Any]) -> bool:
    if not isinstance(activity, dict):
        return False
    return (
        (_safe_number(activity.get("aerobic_te")) or 0.0) >= 4.0
        or (_safe_number(activity.get("anaerobic_te")) or 0.0) >= 1.4
        or (_safe_number(activity.get("training_load")) or 0.0) >= 100.0
    )


def _is_heavy_strength_activity(activity: Dict[str, Any]) -> bool:
    if not isinstance(activity, dict):
        return False
    return (
        (_safe_number(activity.get("training_load")) or 0.0) >= 45.0
        or (_safe_number(activity.get("duration_min")) or 0.0) >= 40.0
        or (_safe_number(activity.get("anaerobic_te")) or 0.0) >= 0.7
    )


def _activity_sport_tag(activity: Dict[str, Any]) -> str:
    sport_tag = activity.get("sport_tag")
    if isinstance(sport_tag, str) and sport_tag:
        return sport_tag
    type_key = str(activity.get("type_key") or "").strip().lower()
    if not type_key:
        return "hybrid"
    if "run" in type_key or "jog" in type_key:
        return "run"
    if "cycl" in type_key or "bike" in type_key or "ride" in type_key:
        return "bike"
    if "strength" in type_key or "weight" in type_key or "yoga" in type_key or "pilates" in type_key:
        return "strength"
    if "walk" in type_key or "hike" in type_key:
        return "recovery"
    return "hybrid"


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


def _parse_iso_day(value: Any):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
