from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional


QUALITY_DAY_TYPES = {"threshold", "vo2"}


def classify_day_intensity(day_item: Dict[str, Any]) -> str:
    activities = day_item.get("activities") or []
    load_day = float(day_item.get("loadDay") or 0.0)
    aero_sum = float(day_item.get("aeroTeSum") or 0.0)
    anaer_sum = float(day_item.get("anaerTeSum") or 0.0)

    if any(_is_vo2_activity(activity) for activity in activities) or aero_sum >= 4.5 or anaer_sum >= 1.8 or load_day >= 120:
        return "vo2"
    if any(_is_threshold_activity(activity) for activity in activities) or aero_sum >= 3.0 or anaer_sum >= 0.8 or load_day >= 75:
        return "threshold"
    if load_day >= 40:
        return "moderate"
    if load_day > 0:
        return "easy"
    return "recovery"


def build_load_snapshot(focus_item: Dict[str, Any], day_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    focus_date = focus_item["date"]
    yesterday = previous_day_item(focus_item, day_items)
    hard_sessions_last_3d = count_quality_days(focus_date, day_items, days=3)
    hard_sessions_last_7d = count_quality_days(focus_date, day_items, days=7)
    ratio = _safe_number(focus_item.get("ratio7to28"))
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
    }


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
