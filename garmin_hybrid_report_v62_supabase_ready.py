#!/usr/bin/env python3
"""
garmin_hybrid_report_v61_full.py

Echte Weiterentwicklung auf Basis der v6-Idee:
- Garmin Login + Datenabruf
- Morning Metrics
- Backfill für letzte N Tage
- History-Pflege
- 7d / 28d Load
- Modi: run | bike | strength | hybrid
- konkrete Einheiten
- KI-Prompt
- Logik:
    * habe ich Morgenwerte und noch kein Training heute -> Empfehlung für heute
    * habe ich Morgenwerte und schon Training heute -> Empfehlung für morgen

Benutzung:
    python garmin_hybrid_report_v61_full.py --days-backfill 28 --days 1 --limit 400
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from garminconnect import Garmin
except Exception:
    print("Missing dependency. Install with: python -m pip install garminconnect", file=sys.stderr)
    raise

from observability import ErrorCategory, get_logger, log_event, log_exception
from training_config import TRAINING_CONFIG


DEFAULT_HISTORY_PATH = "training_history.json"
LOGGER = get_logger(__name__)


STRENGTH_ACTIVITY_LABELS = (
    "strength training",
    "weight training",
    "weight lifting",
    "egym training",
)


@dataclass
class ActivitySummary:
    activity_id: Optional[int]
    start_local: str
    date_local: str
    type_key: str
    name: str
    duration_min: Optional[float]
    distance_km: Optional[float]
    avg_hr: Optional[float]
    max_hr: Optional[float]
    avg_power: Optional[float]
    max_power: Optional[float]
    avg_speed_kmh: Optional[float]
    pace_min_per_km: Optional[str]
    aerobic_te: Optional[float]
    anaerobic_te: Optional[float]
    training_load: Optional[float]


@dataclass
class MorningMetrics:
    date: str
    resting_hr: Optional[float] = None
    hrv: Optional[float] = None
    respiration: Optional[float] = None
    pulse_ox: Optional[float] = None
    sleep_h: Optional[float] = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Garmin hybrid daily report v6.1 full")
    parser.add_argument("--days", type=int, default=1, help="Anzahl Kalendertage für Report-Ausgabe")
    parser.add_argument("--limit", type=int, default=TRAINING_CONFIG.windows.default_activity_limit, help="Anzahl letzter Aktivitäten, die abgefragt werden")
    parser.add_argument("--json", type=str, default="", help="Optionaler JSON-Exportpfad")
    parser.add_argument("--history", type=str, default=DEFAULT_HISTORY_PATH, help="Pfad zur History-Datei")
    parser.add_argument("--baseline-days", type=int, default=TRAINING_CONFIG.windows.baseline_days, help="Tage für Rolling-Baseline")
    parser.add_argument("--days-backfill", type=int, default=0, help="Initiale History für die letzten N Tage aufbauen")
    parser.add_argument("--mode", type=str, default="hybrid", choices=["run", "bike", "strength", "hybrid"], help="Empfehlungsmodus")
    parser.add_argument("--no-morning", action="store_true", help="Morgenwerte nicht abfragen")
    parser.add_argument("--no-debug-json", action="store_true", help="Keine Morning-Debug-JSON schreiben")
    return parser.parse_args()


def load_client(
    email: Optional[str] = None,
    password: Optional[str] = None,
    *,
    session_data: Optional[str] = None,
) -> Garmin:
    email = email or os.getenv("GARMIN_EMAIL")
    password = password or os.getenv("GARMIN_PASSWORD")

    if session_data:
        try:
            client = Garmin()
            client.login(session_data)
            return client
        except Exception as exc:
            log_exception(
                LOGGER,
                category=ErrorCategory.AUTH,
                event="garmin.session_login_failed",
                message="Stored Garmin session rejected, falling back to credentials.",
                exc=exc,
                level=logging.WARNING,
            )

    if not email or not password:
        raise RuntimeError("No valid Garmin session found and Garmin credentials are missing.")

    client = Garmin(email=email, password=password)
    client.login()
    return client


def export_client_session(client: Garmin) -> Optional[str]:
    garth_client = getattr(client, "garth", None)
    if garth_client is None or not hasattr(garth_client, "dumps"):
        log_event(
            LOGGER,
            logging.WARNING,
            category=ErrorCategory.API,
            event="garmin.session_export_missing",
            message="Garmin client does not expose a serializable session.",
        )
        return None

    try:
        return garth_client.dumps()
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.API,
            event="garmin.session_export_failed",
            message="Failed to serialize Garmin session.",
            exc=exc,
            level=logging.WARNING,
        )
        return None


def safe_get(d: Any, *keys: str) -> Any:
    cur = d
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return None if cur == "" else cur


def first_number(*values: Any) -> Optional[float]:
    for v in values:
        if isinstance(v, (int, float)):
            return float(v)
    return None


def to_datetime_local(start_local: Optional[str]) -> Optional[datetime]:
    if not start_local:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(start_local, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(start_local)
    except ValueError:
        return None


def sec_to_min(sec: Optional[float]) -> Optional[float]:
    return round(float(sec) / 60.0, 1) if sec is not None else None


def meter_to_km(m: Optional[float]) -> Optional[float]:
    return round(float(m) / 1000.0, 2) if m is not None else None


def mps_to_kmh(v: Optional[float]) -> Optional[float]:
    return round(float(v) * 3.6, 1) if v is not None else None


def pace_from_speed_mps(v: Optional[float]) -> Optional[str]:
    if v is None or v <= 0:
        return None
    sec_per_km = 1000.0 / float(v)
    minutes = int(sec_per_km // 60)
    seconds = int(round(sec_per_km % 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}/km"


def extract_training_load(activity: Dict[str, Any]) -> Optional[float]:
    candidates = [
        activity.get("trainingLoad"),
        activity.get("activityTrainingLoad"),
        activity.get("anaerobicTrainingLoad"),
        safe_get(activity, "summarizedExerciseSets", "trainingLoad"),
        safe_get(activity, "trainingEffectLabel", "trainingLoad"),
        safe_get(activity, "metadataDTO", "trainingLoad"),
        safe_get(activity, "metadataDto", "trainingLoad"),
        safe_get(activity, "loadDTO", "trainingLoad"),
        safe_get(activity, "activityDetails", "trainingLoad"),
    ]
    return first_number(*candidates)


def is_strength_activity(activity: Dict[str, Any]) -> bool:
    type_candidates = [
        safe_get(activity, "activityType", "typeKey"),
        safe_get(activity, "activityType", "parentTypeKey"),
        safe_get(activity, "activityType", "categoryKey"),
        activity.get("activityTypeKey"),
    ]
    for candidate in type_candidates:
        if _matches_strength_activity_label(candidate):
            return True
    return _matches_strength_activity_label(activity.get("activityName"))


def estimate_strength_load(duration_minutes: Optional[float]) -> Optional[float]:
    if duration_minutes is None or duration_minutes <= 0:
        return None
    return round(min(float(duration_minutes) * 0.8, 60.0), 1)


def _matches_strength_activity_label(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    if not normalized:
        return False
    tokens = set(normalized.split())
    if "strength" in tokens:
        return True
    collapsed = normalized.replace(" ", "")
    return (
        any(label in normalized for label in STRENGTH_ACTIVITY_LABELS)
        or "strengthtraining" in collapsed
        or "weighttraining" in collapsed
        or "weightlifting" in collapsed
    )


def summarize_activity(a: Dict[str, Any]) -> ActivitySummary:
    dt = to_datetime_local(a.get("startTimeLocal"))
    start_local = dt.strftime("%Y-%m-%d %H:%M") if dt else str(a.get("startTimeLocal") or "")
    date_local = dt.strftime("%Y-%m-%d") if dt else ""

    duration_min = sec_to_min(a.get("duration"))
    training_load = extract_training_load(a)
    if is_strength_activity(a):
        estimated_strength_load = estimate_strength_load(duration_min)
        # Garmin HR/EPOC load often undercounts heavy strength work, so apply a simple floor.
        if estimated_strength_load is not None:
            training_load = max(training_load, estimated_strength_load) if training_load is not None else estimated_strength_load

    return ActivitySummary(
        activity_id=a.get("activityId"),
        start_local=start_local,
        date_local=date_local,
        type_key=safe_get(a, "activityType", "typeKey") or "unknown",
        name=a.get("activityName") or (safe_get(a, "activityType", "typeKey") or "unknown"),
        duration_min=duration_min,
        distance_km=meter_to_km(a.get("distance")),
        avg_hr=first_number(a.get("averageHR")),
        max_hr=first_number(a.get("maxHR")),
        avg_power=first_number(a.get("averagePower")),
        max_power=first_number(a.get("maxPower")),
        avg_speed_kmh=mps_to_kmh(a.get("averageSpeed")),
        pace_min_per_km=pace_from_speed_mps(a.get("averageSpeed")),
        aerobic_te=first_number(a.get("aerobicTrainingEffect")),
        anaerobic_te=first_number(a.get("anaerobicTrainingEffect")),
        training_load=round(training_load, 1) if training_load is not None else None,
    )


def get_recent_activities(client: Garmin, limit: int) -> List[ActivitySummary]:
    raw = client.get_activities(0, limit)
    return [summarize_activity(a) for a in raw]


def filter_days(activities: List[ActivitySummary], days: int) -> List[ActivitySummary]:
    today = date.today()
    earliest = today - timedelta(days=days - 1)
    out = []
    for a in activities:
        if not a.date_local:
            continue
        d = datetime.strptime(a.date_local, "%Y-%m-%d").date()
        if d >= earliest:
            out.append(a)
    return out


def try_call(client: Garmin, method_names: List[str], *args: Any, **kwargs: Any) -> Any:
    failures: List[Tuple[str, str]] = []
    for name in method_names:
        fn = getattr(client, name, None)
        if callable(fn):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                failures.append((name, str(exc)))
                continue

    if failures:
        log_event(
            LOGGER,
            logging.WARNING,
            category=ErrorCategory.API,
            event="garmin.method_fallback_exhausted",
            message="All Garmin method fallbacks failed.",
            methods=[name for name, _error in failures],
            errors=[error for _name, error in failures],
        )
    return None


def fetch_morning_bundle(client: Garmin, when: str) -> Dict[str, Any]:
    return {
        "stats": try_call(client, ["get_stats", "get_user_summary", "get_daily_stats"], when),
        "heart_rates": try_call(client, ["get_heart_rates", "get_heart_rate", "get_heart_rate_data"], when),
        "hrv": try_call(client, ["get_hrv_data", "get_hrv", "get_hrv_summary"], when),
        "respiration": try_call(client, ["get_respiration_data", "get_respirations_data", "get_respiration", "get_respiration_rate"], when),
        "spo2": try_call(client, ["get_pulse_ox_data", "get_spo2_data", "get_pulseox_data"], when),
        "sleep": try_call(client, ["get_sleep_data", "get_sleep", "get_sleep_stats"], when),
    }


def fetch_morning_metrics(client: Garmin, when: str) -> Tuple[MorningMetrics, Dict[str, Any]]:
    bundle = fetch_morning_bundle(client, when)
    metrics = MorningMetrics(date=when)

    stats = bundle["stats"] or {}
    hr_data = bundle["heart_rates"] or {}
    hrv_data = bundle["hrv"] or {}
    resp_data = bundle["respiration"] or {}
    spo2_data = bundle["spo2"] or {}
    sleep_data = bundle["sleep"] or {}

    metrics.resting_hr = first_number(
        safe_get(stats, "restingHeartRate"),
        safe_get(stats, "heartRate", "restingHeartRate"),
        safe_get(hr_data, "restingHeartRate"),
    )
    metrics.hrv = first_number(
        safe_get(hrv_data, "hrvSummary", "lastNightAvg"),
        safe_get(hrv_data, "lastNightAvg"),
        safe_get(hrv_data, "hrvSummary", "weeklyAvg"),
        safe_get(hrv_data, "weeklyAvg"),
    )
    metrics.respiration = first_number(
        safe_get(sleep_data, "dailySleepDTO", "averageRespirationValue"),
        safe_get(resp_data, "avgSleepRespirationValue"),
        safe_get(resp_data, "averageRespirationValue"),
        safe_get(resp_data, "avgWakingRespirationValue"),
        safe_get(stats, "avgWakingRespirationValue"),
    )
    metrics.pulse_ox = first_number(
        safe_get(sleep_data, "dailySleepDTO", "averageSpO2Value"),
        safe_get(spo2_data, "avgSleepSpO2"),
        safe_get(spo2_data, "averageSpO2"),
        safe_get(spo2_data, "averageSpo2"),
        safe_get(stats, "averageSpo2"),
    )

    sleep_seconds = first_number(
        safe_get(sleep_data, "dailySleepDTO", "sleepTimeSeconds"),
        safe_get(sleep_data, "sleepTimeSeconds"),
        safe_get(sleep_data, "sleepTime"),
    )
    if sleep_seconds is not None:
        metrics.sleep_h = round(float(sleep_seconds) / 3600.0, 2)

    return metrics, bundle


def fmt(v: Any, suffix: str = "") -> str:
    if v is None or v == "":
        return "-"
    if isinstance(v, float):
        return f"{v:.1f}{suffix}"
    return f"{v}{suffix}"


def aggregate_day(activities: List[ActivitySummary]) -> Dict[str, Optional[float]]:
    total_min = sum(a.duration_min or 0 for a in activities)
    aero_te = sum(a.aerobic_te or 0 for a in activities)
    anaer_te = sum(a.anaerobic_te or 0 for a in activities)
    loads = [a.training_load for a in activities if a.training_load is not None]
    total_load = round(sum(loads), 1) if loads else None
    return {
        "total_min": round(total_min, 1),
        "aero_te_sum": round(aero_te, 1),
        "anaer_te_sum": round(anaer_te, 1),
        "training_load_sum": total_load,
    }


def stress_label(day: Dict[str, Optional[float]]) -> str:
    aero = day.get("aero_te_sum") or 0
    anaer = day.get("anaer_te_sum") or 0
    load = day.get("training_load_sum") or 0
    cfg = TRAINING_CONFIG.stress
    if aero >= cfg.high_aero_te or anaer >= cfg.high_anaerobic_te or load >= cfg.high_load:
        return "hoch"
    if aero >= cfg.moderate_aero_te or anaer >= cfg.moderate_anaerobic_te or load >= cfg.moderate_load:
        return "moderat"
    return "niedrig"


def load_history(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"days": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("days"), dict):
            return data
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.DB,
            event="history.load_failed",
            message="Failed to load training history file.",
            exc=exc,
            level=logging.WARNING,
            path=str(p),
        )
    return {"days": {}}


def save_history(path: str, history: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def update_history(
    history: Dict[str, Any],
    day_str: str,
    morning: Optional[MorningMetrics],
    summary: Dict[str, Optional[float]],
) -> None:
    history.setdefault("days", {})
    history["days"][day_str] = {
        "morning": asdict(morning) if morning else None,
        "summary": summary,
    }


def available_history_days(history: Dict[str, Any], current_day: str, window_days: int, include_current: bool = True) -> int:
    days = history.get("days", {})
    current = datetime.strptime(current_day, "%Y-%m-%d").date()
    earliest = current - timedelta(days=window_days - 1)
    count = 0
    for d, payload in days.items():
        try:
            day_date = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        if day_date < earliest or day_date > current:
            continue
        if not include_current and day_date == current:
            continue
        morning = payload.get("morning") or {}
        summary = payload.get("summary") or {}
        has_data = any(isinstance(morning.get(k), (int, float)) for k in ("hrv", "resting_hr", "respiration", "sleep_h"))
        has_data = has_data or isinstance(summary.get("training_load_sum"), (int, float))
        if has_data:
            count += 1
    return count


def history_window(history: Dict[str, Any], current_day: str, field: str, baseline_days: int) -> List[float]:
    days = history.get("days", {})
    current = datetime.strptime(current_day, "%Y-%m-%d").date()
    earliest = current - timedelta(days=baseline_days)
    vals = []
    for d, payload in days.items():
        try:
            day_date = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (earliest <= day_date < current):
            continue
        morning = payload.get("morning") or {}
        val = morning.get(field)
        if isinstance(val, (int, float)):
            vals.append(float(val))
    return vals


def median_std(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if not values:
        return None, None
    med = statistics.median(values)
    std = statistics.pstdev(values) if len(values) > 1 else 0.0
    return float(med), float(std)


def band_text(value: Optional[float], baseline: Optional[float], std: Optional[float], higher_is_better: bool) -> str:
    if value is None or baseline is None or std is None:
        return "-"
    std = max(std, TRAINING_CONFIG.readiness.std_floor)
    diff = value - baseline
    if not higher_is_better:
        diff = -diff
    if diff >= -std:
        return "grün"
    if diff >= -(2 * std):
        return "gelb"
    return "rot"


def compute_readiness(
    morning: Optional[MorningMetrics],
    history: Dict[str, Any],
    day_str: str,
    baseline_days: int,
    min_samples: int = TRAINING_CONFIG.windows.min_baseline_samples,
) -> Dict[str, Any]:
    if not morning:
        return {"score": None, "bands": {}, "baselines": {}, "reason": "no_morning_metrics"}

    fields = TRAINING_CONFIG.readiness.higher_is_better

    baselines: Dict[str, Any] = {}
    bands: Dict[str, str] = {}
    contributions: List[float] = []

    for field, higher_is_better in fields.items():
        vals = history_window(history, day_str, field, baseline_days)
        baseline, std = median_std(vals)
        current = getattr(morning, field)
        baselines[field] = {"baseline": baseline, "std": std, "n": len(vals)}

        if len(vals) < min_samples:
            bands[field] = "-"
            continue

        bands[field] = band_text(current, baseline, std, higher_is_better)

        if current is not None and baseline is not None and std is not None:
            std_eff = max(std, TRAINING_CONFIG.readiness.std_floor)
            z = (current - baseline) / std_eff
            if not higher_is_better:
                z = -z
            z = max(-TRAINING_CONFIG.readiness.z_clip, min(TRAINING_CONFIG.readiness.z_clip, z))
            contributions.append(z)

    if not contributions:
        return {"score": None, "bands": bands, "baselines": baselines, "reason": "insufficient_baseline_history"}

    avg_z = sum(contributions) / len(contributions)
    score = round(TRAINING_CONFIG.readiness.score_center + avg_z * TRAINING_CONFIG.readiness.score_scale)
    score = max(TRAINING_CONFIG.readiness.min_score, min(TRAINING_CONFIG.readiness.max_score, score))
    return {"score": score, "bands": bands, "baselines": baselines, "reason": None}


def get_day_load(history: Dict[str, Any], day_str: str) -> float:
    payload = history.get("days", {}).get(day_str, {})
    summary = payload.get("summary") or {}
    val = summary.get("training_load_sum")
    return float(val) if isinstance(val, (int, float)) else 0.0


def rolling_load(history: Dict[str, Any], end_day_str: str, window_days: int) -> float:
    end_day = datetime.strptime(end_day_str, "%Y-%m-%d").date()
    total = 0.0
    for i in range(window_days):
        d = end_day - timedelta(days=i)
        total += get_day_load(history, d.isoformat())
    return round(total, 1)


def compute_load_metrics(
    history: Dict[str, Any],
    day_str: str,
    min_history_days: int = TRAINING_CONFIG.windows.min_ratio_history_days,
) -> Dict[str, Optional[float]]:
    acute_days = TRAINING_CONFIG.windows.acute_load_days
    chronic_days = TRAINING_CONFIG.windows.chronic_load_days
    acute_7d = rolling_load(history, day_str, acute_days)
    chronic_28d = rolling_load(history, day_str, chronic_days)

    acute_daily_avg = acute_7d / float(acute_days) if acute_7d > 0 else 0.0
    chronic_daily_avg = chronic_28d / float(chronic_days) if chronic_28d > 0 else 0.0
    history_days = available_history_days(history, day_str, chronic_days, include_current=True)

    ratio = None
    reason = None
    if history_days < min_history_days:
        reason = "insufficient_load_history"
    elif chronic_daily_avg > 0:
        ratio = round(acute_daily_avg / chronic_daily_avg, 2)

    return {
        "load_7d": round(acute_7d, 1),
        "load_28d": round(chronic_28d, 1),
        "load_7d_daily_avg": round(acute_daily_avg, 1),
        "load_28d_daily_avg": round(chronic_daily_avg, 1),
        "load_ratio": ratio,
        "history_days_considered": history_days,
        "load_ratio_reason": reason,
    }


def load_ratio_label(ratio: Optional[float], reason: Optional[str] = None) -> str:
    if ratio is None:
        if reason == "insufficient_load_history":
            return "zu wenig Historie"
        return "-"
    cfg = TRAINING_CONFIG.ratio
    if ratio < cfg.under_target_max:
        return "unter Soll"
    if ratio <= cfg.target_max:
        return "im Zielbereich"
    if ratio <= cfg.elevated_max:
        return "erhöht"
    return "kritisch hoch"


def recommendation(
    morning: Optional[MorningMetrics],
    day: Dict[str, Optional[float]],
    readiness: Dict[str, Any],
    load_metrics: Dict[str, Optional[float]],
    mode: str = "hybrid",
) -> str:
    ratio = load_metrics.get("load_ratio")
    score = readiness.get("score")
    alerts = TRAINING_CONFIG.alerts
    ratio_cfg = TRAINING_CONFIG.ratio

    if morning:
        if (
            (morning.respiration is not None and morning.respiration >= alerts.respiration_high)
            or (morning.hrv is not None and morning.hrv <= alerts.hrv_low)
            or (morning.resting_hr is not None and morning.resting_hr >= alerts.resting_hr_high)
        ):
            return "Nur aktive Erholung / Z1-Z2 locker / Mobility"

    if ratio is not None and ratio > ratio_cfg.elevated_max:
        return "Belastung aktuell zu hoch: nur locker / Erholung / Mobility"

    if not isinstance(score, int):
        return "Training nach Gefühl, Datenlage noch zu dünn"

    band = TRAINING_CONFIG.recommendation_band(mode)

    if mode == "run":
        if score <= band.recovery_max:
            return "Nur locker laufen / Mobility"
        if score <= band.moderate_max:
            return "Lockerer bis aerober Dauerlauf"
        if score <= band.solid_max:
            return "Moderater Lauf, keine harten Intervalle"
        if score <= band.quality_max:
            return "Qualitätstag Run möglich"
        return "Harter Lauf-Qualitätstag gut vertretbar"

    if mode == "bike":
        if score <= band.recovery_max:
            return "Nur locker rollen / Mobility"
        if score <= band.moderate_max:
            return "Lockere bis moderate Radeinheit"
        if score <= band.solid_max:
            return "Moderater Bike-Tag, keine maximalen Intervalle"
        if score <= band.quality_max:
            return "Qualitätstag Bike möglich"
        return "Harter Bike-Intervalltag gut vertretbar"

    if mode == "strength":
        if score <= band.recovery_max:
            return "Nur Mobility oder sehr leichtes Krafttraining"
        if score <= band.moderate_max:
            return "Moderates Krafttraining"
        if score <= band.solid_max:
            return "Normales Krafttraining möglich"
        if score <= band.quality_max:
            return "Schweres Krafttraining möglich"
        return "Schweres Krafttraining sehr gut vertretbar"

    if score <= band.recovery_max:
        return "Nur locker / Erholung / Mobility"
    if score <= band.moderate_max:
        return "Aerober Basistag oder moderates Krafttraining"
    if score <= band.solid_max:
        return "Solider Trainingstag: moderat bis zügig, aber nicht maximal"
    if score <= band.quality_max:
        return "Qualitätstag möglich"
    return "Harter Qualitätstag gut vertretbar"


def suggested_units(score: Optional[int], ratio: Optional[float], mode: str) -> List[str]:
    if score is None:
        return [
            "Datenlage zu dünn: 30-45 min locker nach Gefühl",
            "Optional 10-15 min Mobility",
        ]

    if ratio is not None and ratio > TRAINING_CONFIG.ratio.elevated_max:
        return [
            "30-45 min sehr locker in Z1",
            "oder 20-30 min Mobility / Spazieren",
            "keine harte Qualität, kein schweres Krafttraining",
        ]

    low_band, mid_band, high_band = TRAINING_CONFIG.unit_band(mode)

    if mode == "run":
        if score < low_band:
            return [
                "30-40 min locker laufen oder gehen",
                "optional 6 x 20 s lockere Steigerungen nur wenn Beine gut",
            ]
        if score < mid_band:
            return [
                "45-60 min lockerer bis moderater Dauerlauf",
                "alternativ 30-45 min locker + 6 x 20 s Steigerungen",
            ]
        if score < high_band:
            return [
                "6 x 3 min zügig mit 2 min locker",
                "alternativ 4 x 5 min an Schwelle mit 2-3 min locker",
            ]
        return [
            "5 x 4 min hart mit 3 min locker",
            "alternativ 8 x 400 m zügig mit lockerer Trabpause",
        ]

    if mode == "bike":
        if score < low_band:
            return [
                "45-60 min sehr locker rollen in Z1/Z2",
                "hohe Kadenz, keine Intervalle",
            ]
        if score < mid_band:
            return [
                "60-90 min locker bis moderat in Z2",
                "alternativ 3 x 8 min Sweet Spot kontrolliert",
            ]
        if score < high_band:
            return [
                "4 x 8 min zügig mit 4 min locker",
                "alternativ 5 x 5 min hart mit 3 min locker",
            ]
        return [
            "6 x 4 min VO2 mit 4 min locker",
            "alternativ 3 x 12 min Schwelle mit 6 min locker",
        ]

    if mode == "strength":
        if score < low_band:
            return [
                "Nur Mobility, Technik oder sehr leichte Maschinenrunde",
                "kein schweres Beintraining",
            ]
        if score < mid_band:
            return [
                "Moderates Krafttraining Ganzkörper, 2-3 Sätze",
                "1-3 Wiederholungen im Tank lassen",
            ]
        if score < high_band:
            return [
                "Schweres Krafttraining möglich, Hauptlifts fokussieren",
                "z. B. 3-5 Sätze Grundübungen, moderates Volumen",
            ]
        return [
            "Schwerer Krafttag gut vertretbar",
            "z. B. Hauptübungen schwer + 1-2 Zusatzübungen",
        ]

    # hybrid = run + bike + strength
    if score < low_band:
        return [
            "Run/Bike: 30-40 min locker",
            "Mobility: 20-30 min",
            "Strength: nur leichtes Krafttraining ohne schwere Sätze",
        ]
    if score < mid_band:
        return [
            "Run: 45-60 min locker bis moderat",
            "Bike: 60-90 min locker Z2",
            "Strength: normale eGym-Runde / moderates Ganzkörpertraining",
        ]
    if score < high_band:
        return [
            "Run: 6 x 3 min zügig oder 4 x 5 min Schwelle",
            "Bike: 4 x 8 min zügig oder 5 x 5 min hart",
            "Strength: schweres Krafttraining möglich, aber nicht maximal",
        ]
    return [
        "Run: harter Qualitätstag möglich",
        "Bike: harter Intervalltag möglich",
        "Strength: schwerer Krafttag gut vertretbar",
    ]


def build_training_flags(mode: str, score: Optional[int], ratio: Optional[float]) -> Dict[str, str]:
    flags = {
        "easy": "JA",
        "quality": "NEIN",
        "strength_heavy": "NEIN",
        "max_test": "NEIN",
    }

    if score is None:
        return flags
    if ratio is not None and ratio > TRAINING_CONFIG.ratio.elevated_max:
        return flags

    thresholds = TRAINING_CONFIG.flags_for_mode(mode)
    if score >= thresholds.quality_min:
        flags["quality"] = "JA"
    if score >= thresholds.strength_heavy_min:
        flags["strength_heavy"] = "JA"
    if score >= thresholds.max_test_min:
        flags["max_test"] = "JA"
    return flags


def has_training_today(activities: List[ActivitySummary], day_str: str) -> bool:
    return any(a.date_local == day_str for a in activities)


def infer_target_day(today_str: str, has_morning: bool, trained_today: bool) -> str:
    if not has_morning:
        return today_str
    if trained_today:
        return (datetime.strptime(today_str, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
    return today_str


def build_ai_prompt(
    mode: str,
    recommendation_day: str,
    today_day: str,
    latest_morning: Optional[MorningMetrics],
    today_summary: Dict[str, Optional[float]],
    today_load_metrics: Dict[str, Optional[float]],
    today_activities: List[ActivitySummary],
    dashboard_recommendations: Dict[str, str],
    units: List[str],
) -> str:
    if mode == "run":
        target = "Lauftraining"
    elif mode == "bike":
        target = "Radtraining"
    elif mode == "strength":
        target = "Krafttraining"
    else:
        target = "Hybridtraining aus Run, Bike und Strength"

    acts = []
    for a in today_activities:
        parts = [f"{a.name}", f"{fmt(a.duration_min, ' min')}"]
        if a.avg_hr is not None:
            parts.append(f"ØHF {a.avg_hr:.0f}")
        if a.max_hr is not None:
            parts.append(f"MaxHF {a.max_hr:.0f}")
        if a.aerobic_te is not None:
            parts.append(f"TEa {a.aerobic_te:.1f}")
        if a.anaerobic_te is not None:
            parts.append(f"TEan {a.anaerobic_te:.1f}")
        if a.training_load is not None:
            parts.append(f"Load {a.training_load:.1f}")
        acts.append("- " + " | ".join(parts))
    acts_text = "\n".join(acts) if acts else "- kein Training bisher"

    units_text = "\n".join([f"- {u}" for u in units]) if units else "- keine"

    prompt = f"""Du bist mein nüchterner Trainingsberater. Beurteile nur anhand der folgenden Garmin-Daten, ob für {recommendation_day} eher Erholung, moderates Training oder ein Qualitätstag sinnvoll ist.

Regeln:
- Antworte knapp und konkret.
- Keine Motivation, kein Coaching-Ton, keine medizinischen Aussagen.
- Bevorzuge konservative Entscheidungen, wenn Last oder Tagesform grenzwertig sind.
- Gib am Ende genau diese Punkte aus:
  1. Gesamturteil
  2. Empfohlene Einheit für {recommendation_day}
  3. Was ich vermeiden sollte
  4. Begründung in 3 kurzen Punkten

Datenbasis:
Heute: {today_day}
Empfehlung gilt für: {recommendation_day}
Modus: {mode}
Zielbereich: {target}

Morgenwerte heute:
Readiness: {fmt(today_load_metrics.get('readiness_score'))}/99
Ruhepuls: {fmt(latest_morning.resting_hr if latest_morning else None)}
HRV: {fmt(latest_morning.hrv if latest_morning else None)}
Atmung: {fmt(latest_morning.respiration if latest_morning else None)}
SpO2: {fmt(latest_morning.pulse_ox if latest_morning else None)}
Schlaf: {fmt(latest_morning.sleep_h if latest_morning else None, ' h')}

Belastung:
Tages-Load heute: {fmt(today_summary.get('training_load_sum'))}
7d Load: {fmt(today_load_metrics.get('load_7d'))}
28d Load: {fmt(today_load_metrics.get('load_28d'))}
7d/28d Ratio: {fmt(today_load_metrics.get('load_ratio'))} ({today_load_metrics.get('load_ratio_label')})

Heutige Einheiten:
{acts_text}

Interne Basisausgabe meines Modells:
- Hybrid: {dashboard_recommendations.get('hybrid')}
- Run: {dashboard_recommendations.get('run')}
- Bike: {dashboard_recommendations.get('bike')}
- Strength: {dashboard_recommendations.get('strength')}

Vorgeschlagene Einheiten aus meinem Modell:
{units_text}

Bitte gib eine konkrete Empfehlung für {recommendation_day} für {target}. Falls die Daten eher gegen maximale Intensität sprechen, sage das klar."""
    return prompt


def render_report(
    report_day_str: str,
    activities: List[ActivitySummary],
    morning: Optional[MorningMetrics],
    readiness: Dict[str, Any],
    load_metrics: Dict[str, Optional[float]],
    mode: str,
    recommendation_day: str,
    units: List[str],
) -> str:
    day = aggregate_day(activities)
    flags = build_training_flags(mode, readiness.get("score"), load_metrics.get("load_ratio"))

    lines = [f"=== {report_day_str} ==="]
    lines.append(f"Empfehlung gilt für: {recommendation_day}")

    if morning:
        lines.append(
            f"Morgenwerte: Ruhepuls {fmt(morning.resting_hr)} | HRV {fmt(morning.hrv)} | "
            f"Atmung {fmt(morning.respiration)} | SpO2 {fmt(morning.pulse_ox)} | Schlaf {fmt(morning.sleep_h, ' h')}"
        )

    score = readiness.get("score")
    baselines = readiness.get("baselines", {})
    bands = readiness.get("bands", {})

    if score is not None:
        def base(field: str) -> str:
            return fmt((baselines.get(field) or {}).get("baseline"))

        lines.append(
            f"Readiness: {score}/99 | "
            f"HRV {bands.get('hrv','-')} (Basis {base('hrv')}) | "
            f"Ruhepuls {bands.get('resting_hr','-')} (Basis {base('resting_hr')}) | "
            f"Atmung {bands.get('respiration','-')} (Basis {base('respiration')}) | "
            f"Schlaf {bands.get('sleep_h','-')} (Basis {base('sleep_h')})"
        )

    lines.append(
        f"Load: 7d {fmt(load_metrics.get('load_7d'))} | "
        f"28d {fmt(load_metrics.get('load_28d'))} | "
        f"7d/28d Ratio {fmt(load_metrics.get('load_ratio'))} ({load_ratio_label(load_metrics.get('load_ratio'))})"
    )

    lines.append("Training:")
    for a in sorted(activities, key=lambda x: x.start_local):
        line = f"- {a.start_local} | {a.type_key} | {a.name} | {fmt(a.duration_min, ' min')}"
        if a.distance_km is not None:
            line += f" | {a.distance_km:.2f} km"
        if a.avg_power is not None:
            line += f" | ØW {a.avg_power:.0f}"
        if a.avg_hr is not None:
            line += f" | ØHF {a.avg_hr:.0f}"
        if a.max_hr is not None:
            line += f" | MaxHF {a.max_hr:.0f}"
        if a.aerobic_te is not None:
            line += f" | TEa {a.aerobic_te:.1f}"
        if a.anaerobic_te is not None:
            line += f" | TEan {a.anaerobic_te:.1f}"
        if a.training_load is not None:
            line += f" | Load {a.training_load:.1f}"
        lines.append(line)

    lines.append(
        f"Tagessumme: {fmt(day['total_min'], ' min')} | "
        f"TEa gesamt {fmt(day['aero_te_sum'])} | "
        f"TEan gesamt {fmt(day['anaer_te_sum'])} | "
        f"Load gesamt {fmt(day['training_load_sum'])}"
    )
    lines.append(f"Systemstress: {stress_label(day)}")
    lines.append(f"Empfehlung ({mode}) für {recommendation_day}: {recommendation(morning, day, readiness, load_metrics, mode)}")
    lines.append(
        f"Trainings-Ampel: locker {flags['easy']} | Qualität {flags['quality']} | "
        f"schwer Kraft {flags['strength_heavy']} | Max-Test {flags['max_test']}"
    )
    lines.append("Konkrete Einheiten:")
    for u in units:
        lines.append(f"- {u}")
    return "\n".join(lines)


def build_grouped_by_day(activities: List[ActivitySummary]) -> Dict[str, List[ActivitySummary]]:
    grouped: Dict[str, List[ActivitySummary]] = {}
    for a in activities:
        if not a.date_local:
            continue
        grouped.setdefault(a.date_local, []).append(a)
    return grouped


def daterange_backwards(days: int) -> List[str]:
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


def backfill_history(
    client: Garmin,
    history: Dict[str, Any],
    activities_by_day: Dict[str, List[ActivitySummary]],
    days_backfill: int,
    no_morning: bool,
    no_debug_json: bool,
) -> None:
    if days_backfill <= 0:
        return

    today_str = date.today().isoformat()

    for day_str in sorted(daterange_backwards(days_backfill)):
        day_activities = activities_by_day.get(day_str, [])
        morning = None
        bundle = None

        if not no_morning:
            try:
                morning, bundle = fetch_morning_metrics(client, day_str)
            except Exception as exc:
                log_exception(
                    LOGGER,
                    category=ErrorCategory.API,
                    event="garmin.backfill_morning_failed",
                    message="Morning metric fetch failed during backfill.",
                    exc=exc,
                    level=logging.WARNING,
                    day=day_str,
                )
                morning = None
                bundle = None

        summary = aggregate_day(day_activities)
        update_history(history, day_str, morning, summary)

        if bundle is not None and not no_debug_json and day_str == today_str:
            debug_name = f"{day_str.replace('-', '')}-morningdebug.json"
            Path(debug_name).write_text(
                json.dumps(bundle, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )


def main() -> int:
    args = parse_args()
    client = load_client()
    history = load_history(args.history)

    recent_activities = get_recent_activities(client, args.limit)
    activities_by_day = build_grouped_by_day(recent_activities)

    if args.days_backfill > 0:
        backfill_history(
            client=client,
            history=history,
            activities_by_day=activities_by_day,
            days_backfill=args.days_backfill,
            no_morning=args.no_morning,
            no_debug_json=args.no_debug_json,
        )
        save_history(args.history, history)

    visible_activities = filter_days(recent_activities, args.days)

    if not visible_activities:
        print("Keine Aktivitäten im gewählten Zeitraum gefunden.")
        if args.days_backfill > 0:
            print(f"History updated with backfill: {args.history}")
        return 0

    grouped = build_grouped_by_day(visible_activities)
    export_payload = []

    for day_str in sorted(grouped.keys(), reverse=True):
        morning = None
        bundle = None

        if not args.no_morning:
            morning, bundle = fetch_morning_metrics(client, day_str)

        summary = aggregate_day(grouped[day_str])
        update_history(history, day_str, morning, summary)

        readiness = compute_readiness(morning, history, day_str, args.baseline_days)
        load_metrics = compute_load_metrics(history, day_str)
        load_metrics["load_ratio_label"] = load_ratio_label(load_metrics.get("load_ratio"), load_metrics.get("load_ratio_reason"))
        load_metrics["readiness_score"] = readiness.get("score")

        trained_today = has_training_today(recent_activities, day_str)
        recommendation_day = infer_target_day(day_str, morning is not None, trained_today)

        units = suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), args.mode)

        recs = {
            "hybrid": recommendation(morning, summary, readiness, load_metrics, "hybrid"),
            "run": recommendation(morning, summary, readiness, load_metrics, "run"),
            "bike": recommendation(morning, summary, readiness, load_metrics, "bike"),
            "strength": recommendation(morning, summary, readiness, load_metrics, "strength"),
        }

        ai_prompt = build_ai_prompt(
            mode=args.mode,
            recommendation_day=recommendation_day,
            today_day=day_str,
            latest_morning=morning,
            today_summary=summary,
            today_load_metrics=load_metrics,
            today_activities=grouped[day_str],
            dashboard_recommendations=recs,
            units=units,
        )

        report = render_report(day_str, grouped[day_str], morning, readiness, load_metrics, args.mode, recommendation_day, units)
        print(report)
        print()

        txt_name = f"{day_str.replace('-', '')}-dailyreportgarmin.txt"
        Path(txt_name).write_text(report + "\n", encoding="utf-8")

        prompt_name = f"{day_str.replace('-', '')}-ai-prompt.txt"
        Path(prompt_name).write_text(ai_prompt + "\n", encoding="utf-8")

        if bundle is not None and not args.no_debug_json:
            debug_name = f"{day_str.replace('-', '')}-morningdebug.json"
            Path(debug_name).write_text(
                json.dumps(bundle, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

        export_payload.append({
            "date": day_str,
            "recommendation_day": recommendation_day,
            "mode": args.mode,
            "morning": asdict(morning) if morning else None,
            "activities": [asdict(a) for a in grouped[day_str]],
            "summary": summary,
            "readiness": readiness,
            "load_metrics": load_metrics,
            "recommendations": recs,
            "units": {
                "hybrid": suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), "hybrid"),
                "run": suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), "run"),
                "bike": suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), "bike"),
                "strength": suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), "strength"),
            },
            "ai_prompt": ai_prompt,
        })

    save_history(args.history, history)

    if args.json:
        Path(args.json).write_text(
            json.dumps(export_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"JSON written to: {args.json}")

    print(f"History updated: {args.history}")
    return 0
def main_logic_for_day(
    day: str,
    mode: str = "hybrid",
    history: Optional[Dict[str, Any]] = None,
    client: Optional[Garmin] = None,
    recent_activities: Optional[List[ActivitySummary]] = None,
    baseline_days: int = TRAINING_CONFIG.windows.baseline_days,
    persist_history: bool = False,
) -> dict:
    client = client or load_client()
    history = history if history is not None else load_history(DEFAULT_HISTORY_PATH)

    if recent_activities is None:
        recent_activities = get_recent_activities(client, TRAINING_CONFIG.windows.default_activity_limit)

    activities_for_day = [a for a in recent_activities if a.date_local == day]

    morning = None
    try:
        morning, _bundle = fetch_morning_metrics(client, day)
    except Exception as exc:
        log_exception(
            LOGGER,
            category=ErrorCategory.API,
            event="garmin.morning_metrics_failed",
            message="Morning metric fetch failed for requested day.",
            exc=exc,
            level=logging.WARNING,
            day=day,
        )
        morning = None

    summary = aggregate_day(activities_for_day)
    update_history(history, day, morning, summary)

    readiness = compute_readiness(morning, history, day, baseline_days)
    load_metrics = compute_load_metrics(history, day)
    load_metrics["load_ratio_label"] = load_ratio_label(load_metrics.get("load_ratio"), load_metrics.get("load_ratio_reason"))
    load_metrics["readiness_score"] = readiness.get("score")

    trained_that_day = len(activities_for_day) > 0
    recommendation_day = infer_target_day(day, morning is not None, trained_that_day)

    recs = {
        "hybrid": recommendation(morning, summary, readiness, load_metrics, "hybrid"),
        "run": recommendation(morning, summary, readiness, load_metrics, "run"),
        "bike": recommendation(morning, summary, readiness, load_metrics, "bike"),
        "strength": recommendation(morning, summary, readiness, load_metrics, "strength"),
    }

    units = {
        "hybrid": suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), "hybrid"),
        "run": suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), "run"),
        "bike": suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), "bike"),
        "strength": suggested_units(readiness.get("score"), load_metrics.get("load_ratio"), "strength"),
    }

    ai_prompt = build_ai_prompt(
        mode=mode,
        recommendation_day=recommendation_day,
        today_day=day,
        latest_morning=morning,
        today_summary=summary,
        today_load_metrics=load_metrics,
        today_activities=activities_for_day,
        dashboard_recommendations=recs,
        units=units.get(mode, units["hybrid"]),
    )

    payload = {
        "date": day,
        "recommendation_day": recommendation_day,
        "mode": mode,
        "morning": asdict(morning) if morning else None,
        "activities": [asdict(a) for a in activities_for_day],
        "summary": summary,
        "readiness": readiness,
        "load_metrics": load_metrics,
        "recommendations": recs,
        "units": units,
        "ai_prompt": ai_prompt,
    }

    if persist_history:
        save_history(DEFAULT_HISTORY_PATH, history)

    return payload

    
def main_logic(mode: str = "hybrid") -> dict:
    return main_logic_for_day(date.today().isoformat(), mode, persist_history=True)

if __name__ == "__main__":
    raise SystemExit(main())
