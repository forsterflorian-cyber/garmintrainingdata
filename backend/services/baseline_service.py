from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


METRIC_CONFIG = (
    ("hrv", "HRV", "higher"),
    ("restingHr", "Resting HR", "lower"),
    ("sleepHours", "Sleep", "higher"),
    ("respiration", "Respiration", "lower"),
)


def build_today_metrics(morning: Dict[str, Any], readiness_score: Optional[int]) -> Dict[str, Optional[float]]:
    return {
        "readiness": readiness_score,
        "hrv": _safe_number(morning.get("hrv")),
        "restingHr": _safe_number(morning.get("resting_hr")),
        "sleepHours": _safe_number(morning.get("sleep_h")),
        "respiration": _safe_number(morning.get("respiration")),
    }


def build_baseline_metrics_snapshot(readiness_payload: Dict[str, Any]) -> Dict[str, Optional[float]]:
    baselines = readiness_payload.get("baselines") or {}
    return {
        "hrv": _safe_number((baselines.get("hrv") or {}).get("baseline")),
        "restingHr": _safe_number((baselines.get("resting_hr") or {}).get("baseline")),
        "sleepHours": _safe_number((baselines.get("sleep_h") or {}).get("baseline")),
        "respiration": _safe_number((baselines.get("respiration") or {}).get("baseline")),
    }


def build_comparisons(today: Dict[str, Optional[float]], baseline: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    return {
        "hrvDeltaPct": _delta_pct(today.get("hrv"), baseline.get("hrv")),
        "restingHrDeltaPct": _delta_pct(today.get("restingHr"), baseline.get("restingHr")),
        "sleepDeltaPct": _delta_pct(today.get("sleepHours"), baseline.get("sleepHours")),
        "respirationDeltaPct": _delta_pct(today.get("respiration"), baseline.get("respiration")),
    }


def build_metric_delta_bars(
    today: Dict[str, Optional[float]],
    baseline: Dict[str, Optional[float]],
) -> List[Dict[str, Any]]:
    comparisons = build_comparisons(today, baseline)
    bars: List[Dict[str, Any]] = []

    for key, label, directionality in METRIC_CONFIG:
        delta_key = _comparison_key(key)
        normalized = normalized_deviation(today.get(key), baseline.get(key), directionality)
        tone = metric_tone(normalized)
        progress = 0 if normalized is None else round(((normalized + 1.0) / 2.0) * 100)
        bars.append(
            {
                "key": key,
                "label": label,
                "value": today.get(key),
                "baseline": baseline.get(key),
                "deltaPct": comparisons.get(delta_key),
                "directionality": directionality,
                "normalizedDeviation": normalized,
                "tone": tone,
                "progress": max(0, min(100, progress)),
            }
        )

    return bars


def normalized_deviation(
    today_value: Optional[float],
    baseline_value: Optional[float],
    directionality: str,
) -> Optional[float]:
    if today_value in (None, 0) and baseline_value in (None, 0):
        return None
    if baseline_value in (None, 0) or today_value is None:
        return None

    if directionality == "lower":
        deviation = (float(baseline_value) - float(today_value)) / float(baseline_value)
    else:
        deviation = (float(today_value) - float(baseline_value)) / float(baseline_value)
    return max(-1.0, min(1.0, round(deviation, 4)))


def metric_tone(normalized: Optional[float]) -> str:
    if normalized is None:
        return "neutral"
    if normalized >= 0.10:
        return "positive"
    if normalized >= -0.10:
        return "warning"
    return "critical"


def _comparison_key(metric_key: str) -> str:
    return {
        "hrv": "hrvDeltaPct",
        "restingHr": "restingHrDeltaPct",
        "sleepHours": "sleepDeltaPct",
        "respiration": "respirationDeltaPct",
    }[metric_key]


def _delta_pct(value: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if value is None or baseline in (None, 0):
        return None
    return round(((float(value) - float(baseline)) / float(baseline)) * 100.0, 1)


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
