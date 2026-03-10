from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.services.forecast_service import build_tomorrow_impacts
from backend.services.session_catalog import get_session


def compute_training_decision(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    today = input_payload.get("today") or {}
    baseline = input_payload.get("baseline") or {}
    load = input_payload.get("load") or {}
    comparisons = input_payload.get("comparisons") or {}
    mode = input_payload.get("mode") or "hybrid"

    recovery = compute_recovery_layer(today=today, baseline=baseline)
    load_tolerance = compute_load_tolerance_layer(load=load)
    intensity = compute_intensity_permission(
        today=today,
        baseline=baseline,
        load=load,
        comparisons=comparisons,
        recovery=recovery,
        load_tolerance=load_tolerance,
    )
    strength = compute_strength_permission(recovery=recovery, intensity_permission=intensity["value"], load_tolerance=load_tolerance)
    confidence = compute_confidence(today=today, baseline=baseline, load=load)

    primary_recommendation = pick_primary_recommendation(
        recovery=recovery,
        load_tolerance=load_tolerance,
        intensity=intensity,
        strength=strength,
    )
    best_options = build_best_options(
        intensity_permission=intensity["value"],
        recovery_status=recovery["status"],
        primary_recommendation=primary_recommendation,
        strength_permission=strength["value"],
        mode=mode,
    )
    avoid = build_avoid_list(
        recovery=recovery,
        load_tolerance=load_tolerance,
        intensity=intensity,
        strength=strength,
    )
    why = build_why_lines(
        comparisons=comparisons,
        load=load,
        today=today,
    )
    summary_text = build_summary_text(recovery=recovery, load_tolerance=load_tolerance, intensity=intensity)
    tomorrow_impact = build_tomorrow_impacts(
        recovery_score=float(recovery["score"]),
        hard_sessions_last_3d=int(load.get("hardSessionsLast3d") or 0),
        best_options=best_options,
    )
    trace = build_decision_trace(
        recovery=recovery,
        load_tolerance=load_tolerance,
        intensity=intensity,
        strength=strength,
    )

    return {
        "recoveryScore": recovery["score"],
        "recoveryStatus": recovery["status"],
        "loadToleranceScore": load_tolerance["score"],
        "loadTolerance": load_tolerance["status"],
        "intensityPermission": intensity["value"],
        "primaryRecommendation": primary_recommendation,
        "confidence": confidence["value"],
        "summaryText": summary_text,
        "why": why,
        "avoid": avoid,
        "bestOptions": best_options,
        "tomorrowImpact": tomorrow_impact,
        "statusChips": [
            {"label": "Recovery", "value": recovery["status"], "tone": recovery["tone"]},
            {"label": "Load", "value": load_tolerance["status"], "tone": load_tolerance["tone"]},
            {"label": "Intensity", "value": intensity["label"], "tone": intensity["tone"]},
            {"label": "Confidence", "value": confidence["value"], "tone": confidence["tone"]},
        ],
        "strengthGuidance": strength["label"],
        "debug": {
            "recoveryScore": recovery["score"],
            "loadToleranceScore": load_tolerance["score"],
            "ratio7to28": load.get("ratio7to28"),
            "hardSessionsLast3d": load.get("hardSessionsLast3d"),
            "selectedRulePath": trace,
        },
    }


def compute_recovery_layer(*, today: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    trace: List[str] = []
    weighted_sum = 0.0
    available_weight = 0.0

    recovery_inputs = (
        ("hrv", 0.35, "higher"),
        ("restingHr", 0.25, "lower"),
        ("sleepHours", 0.20, "higher"),
        ("respiration", 0.10, "lower"),
    )

    for key, weight, directionality in recovery_inputs:
        value = normalized_deviation(today.get(key), baseline.get(key), directionality)
        if value is None:
            trace.append(f"{key}: missing")
            continue
        weighted_sum += weight * value
        available_weight += weight
        trace.append(f"{key}: {value:+.2f}")

    readiness_component = readiness_to_component(today.get("readiness"))
    if readiness_component is not None:
        weighted_sum += 0.10 * readiness_component
        available_weight += 0.10
        trace.append(f"readiness: {readiness_component:+.2f}")
    else:
        trace.append("readiness: missing")

    if available_weight <= 0:
        score = -0.05
        status = "Borderline"
    else:
        score = round(weighted_sum / available_weight, 2)
        status = recovery_status_from_score(score)

    return {
        "score": score,
        "status": status,
        "tone": tone_for_recovery_status(status),
        "trace": trace,
    }


def compute_load_tolerance_layer(*, load: Dict[str, Any]) -> Dict[str, Any]:
    trace: List[str] = []
    score = 0.0
    ratio = load.get("ratio7to28")
    hard_sessions_last_3d = int(load.get("hardSessionsLast3d") or 0)
    very_high_yesterday = bool(load.get("veryHighYesterdayLoad"))

    if ratio is None:
        trace.append("ratio: missing")
    elif ratio < 0.8:
        score += 0.25
        trace.append("ratio underloaded: +0.25")
    elif ratio <= 1.1:
        score += 0.10
        trace.append("ratio normal: +0.10")
    elif ratio <= 1.3:
        score -= 0.15
        trace.append("ratio elevated: -0.15")
    else:
        score -= 0.40
        trace.append("ratio high: -0.40")

    if hard_sessions_last_3d <= 0:
        score += 0.20
        trace.append("no hard sessions in last 3d: +0.20")
    elif hard_sessions_last_3d == 1:
        trace.append("one hard session in last 3d: +0.00")
    else:
        score -= 0.30
        trace.append("2+ hard sessions in last 3d: -0.30")

    if very_high_yesterday:
        score -= 0.20
        trace.append("very high yesterday load: -0.20")

    score = round(score, 2)
    status = load_tolerance_status_from_score(score)
    return {
        "score": score,
        "status": status,
        "tone": tone_for_load_tolerance(status),
        "trace": trace,
    }


def compute_intensity_permission(
    *,
    today: Dict[str, Any],
    baseline: Dict[str, Any],
    load: Dict[str, Any],
    comparisons: Dict[str, Any],
    recovery: Dict[str, Any],
    load_tolerance: Dict[str, Any],
) -> Dict[str, Any]:
    trace: List[str] = []
    ratio = _safe_number(load.get("ratio7to28"))
    hrv_delta_pct = _safe_number(comparisons.get("hrvDeltaPct"))
    sleep_delta_pct = _safe_number(comparisons.get("sleepDeltaPct"))
    respiration_delta_pct = _safe_number(comparisons.get("respirationDeltaPct"))
    resting_hr_delta_bpm = delta_bpm(today.get("restingHr"), baseline.get("restingHr"))
    quality_yesterday = load.get("yesterdaySessionType") in {"threshold", "vo2"}

    hrv_suppressed = hrv_delta_pct is not None and hrv_delta_pct <= -12.0
    hrv_not_too_low = hrv_delta_pct is None or hrv_delta_pct >= -5.0
    rhr_elevated = resting_hr_delta_bpm is not None and resting_hr_delta_bpm >= 3.0
    rhr_ok_for_vo2 = resting_hr_delta_bpm is None or resting_hr_delta_bpm <= 3.0
    sleep_very_low = sleep_delta_pct is not None and sleep_delta_pct <= -15.0
    respiration_elevated = respiration_delta_pct is not None and respiration_delta_pct >= 5.0

    if recovery["status"] == "Poor":
        trace.append("recovery poor -> no intensity")
        return {"value": "none", "label": "none", "tone": "critical", "trace": trace, "recoveryDay": True}
    if ratio is not None and ratio > 1.3:
        trace.append("ratio > 1.3 -> no intensity")
        return {"value": "none", "label": "none", "tone": "critical", "trace": trace, "recoveryDay": True}
    if hrv_suppressed and rhr_elevated:
        trace.append("HRV strongly suppressed plus RHR elevated -> no intensity")
        return {"value": "none", "label": "none", "tone": "critical", "trace": trace, "recoveryDay": True}
    if sleep_very_low and respiration_elevated:
        trace.append("sleep very low plus respiration elevated -> no intensity")
        return {"value": "none", "label": "none", "tone": "critical", "trace": trace, "recoveryDay": True}

    readiness_score = int(today.get("readiness") or 0) if today.get("readiness") is not None else None

    if (
        recovery["status"] == "Good"
        and load_tolerance["status"] in {"High", "Normal"}
        and not quality_yesterday
        and (readiness_score is None or readiness_score >= 65)
        and hrv_not_too_low
        and rhr_ok_for_vo2
    ):
        trace.append("VO2 allowed")
        return {"value": "vo2", "label": "VO2", "tone": "positive", "trace": trace, "recoveryDay": False}

    consecutive_quality_allowed = recovery["status"] == "Good" and (ratio is None or ratio < 1.0)
    if (
        recovery["status"] in {"Good", "Stable"}
        and load_tolerance["status"] != "Low"
        and (not quality_yesterday or consecutive_quality_allowed)
    ):
        trace.append("threshold allowed")
        return {"value": "threshold", "label": "Threshold", "tone": "warning", "trace": trace, "recoveryDay": False}

    if recovery["status"] != "Poor" and load_tolerance["status"] != "Low":
        trace.append("moderate allowed")
        return {"value": "moderate", "label": "Moderate", "tone": "warning", "trace": trace, "recoveryDay": False}

    trace.append("mixed signals -> no quality")
    return {"value": "none", "label": "none", "tone": "critical", "trace": trace, "recoveryDay": False}


def compute_strength_permission(
    *,
    recovery: Dict[str, Any],
    intensity_permission: str,
    load_tolerance: Dict[str, Any],
) -> Dict[str, str]:
    if recovery["status"] == "Poor":
        return {"value": "avoid_heavy", "label": "Avoid heavy lower-body strength"}
    if intensity_permission in {"vo2", "threshold"}:
        return {"value": "light_accessory", "label": "Strength only as light accessory"}
    if recovery["status"] in {"Good", "Stable"} and load_tolerance["status"] in {"High", "Normal"}:
        return {"value": "hypertrophy_ok", "label": "Hypertrophy strength is acceptable"}
    return {"value": "maintenance_ok", "label": "Strength maintenance only"}


def compute_confidence(*, today: Dict[str, Any], baseline: Dict[str, Any], load: Dict[str, Any]) -> Dict[str, str]:
    available_recovery_inputs = sum(
        1
        for key in ("hrv", "restingHr", "sleepHours", "respiration")
        if today.get(key) is not None and baseline.get(key) not in (None, 0)
    )
    readiness_available = today.get("readiness") is not None
    load_available = load.get("ratio7to28") is not None
    history_available = load.get("hardSessionsLast3d") is not None and load.get("hardSessionsLast7d") is not None

    if available_recovery_inputs >= 4 and load_available and history_available:
        return {"value": "High", "tone": "positive"}
    if (available_recovery_inputs >= 2 and load_available) or (available_recovery_inputs >= 3 and readiness_available):
        return {"value": "Medium", "tone": "warning"}
    return {"value": "Low", "tone": "critical"}


def pick_primary_recommendation(
    *,
    recovery: Dict[str, Any],
    load_tolerance: Dict[str, Any],
    intensity: Dict[str, Any],
    strength: Dict[str, Any],
) -> str:
    if intensity["recoveryDay"]:
        if load_tolerance["status"] == "Low":
            return "Avoid intensity"
        return "Recovery day"
    if intensity["value"] == "vo2":
        return "VO2max OK"
    if intensity["value"] == "threshold":
        return "Threshold OK"
    if intensity["value"] == "moderate":
        if strength["value"] == "hypertrophy_ok" and load_tolerance["status"] in {"Reduced", "Normal"}:
            return "Strength OK"
        return "Moderate only"
    if recovery["status"] in {"Borderline", "Poor"} or load_tolerance["status"] in {"Reduced", "Low"}:
        return "Easy Aerobic"
    return "Easy Aerobic"


def build_best_options(
    *,
    intensity_permission: str,
    recovery_status: str,
    primary_recommendation: str,
    strength_permission: str,
    mode: str,
) -> List[Dict[str, Any]]:
    if primary_recommendation in {"Recovery day", "Avoid intensity"}:
        option_ids = ["walk_mobility", "easy_spin", "no_structured_intensity"]
    elif intensity_permission == "vo2":
        option_ids = ["vo2_run", "vo2_ride", "threshold_alternative"]
    elif intensity_permission == "threshold":
        option_ids = ["threshold_run", "threshold_ride", "moderate_endurance"]
    elif intensity_permission == "moderate":
        if strength_permission == "hypertrophy_ok" and mode == "strength":
            option_ids = ["strength_hypertrophy", "moderate_ride", "moderate_run"]
        elif primary_recommendation == "Strength OK":
            option_ids = ["strength_hypertrophy", "moderate_ride", "moderate_run"]
        else:
            option_ids = ["moderate_ride", "moderate_run", "strength_maintenance"]
    elif recovery_status == "Poor":
        option_ids = ["walk_mobility", "easy_spin", "no_structured_intensity"]
    else:
        option_ids = ["easy_ride", "easy_run", "strength_light"]

    option_ids = prioritize_for_mode(option_ids, mode)
    return [session_to_best_option(get_session(option_id)) for option_id in option_ids[:3]]


def build_avoid_list(
    *,
    recovery: Dict[str, Any],
    load_tolerance: Dict[str, Any],
    intensity: Dict[str, Any],
    strength: Dict[str, Any],
) -> List[str]:
    avoid: List[str] = []

    if intensity["value"] != "vo2":
        avoid.append("VO2 intervals")
    if intensity["value"] not in {"vo2", "threshold"}:
        avoid.append("Threshold work")
    if load_tolerance["status"] in {"Reduced", "Low"}:
        avoid.append("Extra volume on top of current load")
    if strength["value"] != "hypertrophy_ok":
        avoid.append("Heavy lower-body strength")
    if recovery["status"] == "Poor":
        avoid.append("Any session that pushes pace or power")

    deduped: List[str] = []
    for item in avoid:
        if item not in deduped:
            deduped.append(item)
    return deduped[:3]


def build_why_lines(*, comparisons: Dict[str, Any], load: Dict[str, Any], today: Dict[str, Any]) -> List[str]:
    lines: List[str] = []

    hrv_delta = comparisons.get("hrvDeltaPct")
    resting_hr_delta = comparisons.get("restingHrDeltaPct")
    sleep_delta = comparisons.get("sleepDeltaPct")
    respiration_delta = comparisons.get("respirationDeltaPct")

    if hrv_delta is not None:
        lines.append(f"HRV {hrv_delta:+.1f}% vs baseline")
    if resting_hr_delta is not None:
        lines.append(f"Resting HR {resting_hr_delta:+.1f}% vs baseline")
    if sleep_delta is not None:
        lines.append(f"Sleep {sleep_delta:+.1f}% vs baseline")
    if respiration_delta is not None:
        lines.append(f"Respiration {respiration_delta:+.1f}% vs baseline")

    ratio = load.get("ratio7to28")
    if ratio is not None:
        lines.append(f"7d/28d load ratio {ratio:.2f} {ratio_label(ratio)}")

    hard_sessions_last_3d = int(load.get("hardSessionsLast3d") or 0)
    if hard_sessions_last_3d <= 0:
        lines.append("No excessive recent intensity")
    else:
        lines.append(f"{hard_sessions_last_3d} hard session(s) in the last 3 days")

    if today.get("readiness") is not None and len(lines) < 5:
        lines.append(f"Garmin readiness {int(today['readiness'])}")

    return lines[:5]


def build_summary_text(*, recovery: Dict[str, Any], load_tolerance: Dict[str, Any], intensity: Dict[str, Any]) -> str:
    intensity_text = {
        "vo2": "VO2 work is allowed.",
        "threshold": "Threshold work is allowed.",
        "moderate": "Keep it moderate.",
        "none": "Do not chase intensity.",
    }[intensity["value"]]
    return (
        f"Recovery {recovery['status'].lower()}, "
        f"load tolerance {load_tolerance['status'].lower()}, "
        f"{intensity_text}"
    )


def build_decision_trace(
    *,
    recovery: Dict[str, Any],
    load_tolerance: Dict[str, Any],
    intensity: Dict[str, Any],
    strength: Dict[str, Any],
) -> List[str]:
    return [
        f"recovery={recovery['status']}",
        f"loadTolerance={load_tolerance['status']}",
        *intensity["trace"],
        f"strength={strength['value']}",
    ]


def session_to_best_option(session: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": session["id"],
        "label": session["label"],
        "details": session["details"],
        "fatigueCost": session["fatigueCost"],
        "fatigueLevel": session["fatigueLabel"],
        "sportTag": session["sportTag"],
    }


def prioritize_for_mode(option_ids: List[str], mode: str) -> List[str]:
    if mode not in {"run", "bike", "strength"}:
        return option_ids

    preferred_tag = mode

    def sort_key(option_id: str) -> tuple[int, int]:
        session = get_session(option_id)
        sport_tag = session["sportTag"]
        is_preferred = 0 if sport_tag == preferred_tag else 1
        hybrid_penalty = 1 if sport_tag == "hybrid" else 0
        return (is_preferred, hybrid_penalty)

    return sorted(option_ids, key=sort_key)


def readiness_to_component(readiness: Optional[float]) -> Optional[float]:
    if readiness is None:
        return None
    readiness_value = float(readiness)
    if readiness_value >= 80:
        return 0.6
    if readiness_value >= 70:
        return 0.3
    if readiness_value >= 60:
        return 0.0
    if readiness_value >= 50:
        return -0.3
    return -0.6


def normalized_deviation(today_value: Optional[float], baseline_value: Optional[float], directionality: str) -> Optional[float]:
    if today_value is None or baseline_value in (None, 0):
        return None
    if directionality == "lower":
        deviation = (float(baseline_value) - float(today_value)) / float(baseline_value)
    else:
        deviation = (float(today_value) - float(baseline_value)) / float(baseline_value)
    return max(-1.0, min(1.0, deviation))


def recovery_status_from_score(score: float) -> str:
    if score >= 0.35:
        return "Good"
    if score >= 0.10:
        return "Stable"
    if score >= -0.15:
        return "Borderline"
    return "Poor"


def load_tolerance_status_from_score(score: float) -> str:
    if score >= 0.20:
        return "High"
    if score >= -0.05:
        return "Normal"
    if score >= -0.30:
        return "Reduced"
    return "Low"


def tone_for_recovery_status(status: str) -> str:
    return {
        "Good": "positive",
        "Stable": "warning",
        "Borderline": "warning",
        "Poor": "critical",
    }[status]


def tone_for_load_tolerance(status: str) -> str:
    return {
        "High": "positive",
        "Normal": "positive",
        "Reduced": "warning",
        "Low": "critical",
    }[status]


def ratio_label(ratio: float) -> str:
    if ratio < 0.8:
        return "(underloaded)"
    if ratio <= 1.1:
        return "(target range)"
    if ratio <= 1.3:
        return "(elevated)"
    return "(high)"


def delta_bpm(today_value: Optional[float], baseline_value: Optional[float]) -> Optional[float]:
    if today_value is None or baseline_value is None:
        return None
    return round(float(today_value) - float(baseline_value), 1)


def _safe_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None
