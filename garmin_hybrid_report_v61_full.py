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
import os
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from garminconnect import Garmin
    import garth
except Exception:
    print("Missing dependency. Install with: python -m pip install garminconnect", file=sys.stderr)
    raise


DEFAULT_TOKENS_PATH = os.getenv("GARMIN_TOKENS_PATH", str(Path.home() / ".garminconnect"))
DEFAULT_HISTORY_PATH = "training_history.json"


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
    parser.add_argument("--limit", type=int, default=400, help="Anzahl letzter Aktivitäten, die abgefragt werden")
    parser.add_argument("--json", type=str, default="", help="Optionaler JSON-Exportpfad")
    parser.add_argument("--history", type=str, default=DEFAULT_HISTORY_PATH, help="Pfad zur History-Datei")
    parser.add_argument("--baseline-days", type=int, default=21, help="Tage für Rolling-Baseline")
    parser.add_argument("--days-backfill", type=int, default=0, help="Initiale History für die letzten N Tage aufbauen")
    parser.add_argument("--mode", type=str, default="hybrid", choices=["run", "bike", "strength", "hybrid"], help="Empfehlungsmodus")
    parser.add_argument("--no-morning", action="store_true", help="Morgenwerte nicht abfragen")
    parser.add_argument("--no-debug-json", action="store_true", help="Keine Morning-Debug-JSON schreiben")
    return parser.parse_args()


def load_client() -> Garmin:
    tokens_path = Path(DEFAULT_TOKENS_PATH)
    tokens_path.parent.mkdir(parents=True, exist_ok=True)

    email = os.getenv("GARMIN_EMAIL", "")
    password = os.getenv("GARMIN_PASSWORD", "")

    if tokens_path.exists():
        try:
            client = Garmin()
            client.login(str(tokens_path))
            return client
        except Exception:
            pass

    if not email or not password:
        raise RuntimeError("No valid Garmin tokens found and GARMIN_EMAIL / GARMIN_PASSWORD are not set.")

    client = Garmin(email=email, password=password)
    client.login()

    try:
        garth.dump(str(tokens_path))
    except Exception:
        pass

    return client


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
            pass
    try:
        return datetime.fromisoformat(start_local)
    except Exception:
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


def summarize_activity(a: Dict[str, Any]) -> ActivitySummary:
    dt = to_datetime_local(a.get("startTimeLocal"))
    start_local = dt.strftime("%Y-%m-%d %H:%M") if dt else str(a.get("startTimeLocal") or "")
    date_local = dt.strftime("%Y-%m-%d") if dt else ""

    training_load = extract_training_load(a)

    return ActivitySummary(
        activity_id=a.get("activityId"),
        start_local=start_local,
        date_local=date_local,
        type_key=safe_get(a, "activityType", "typeKey") or "unknown",
        name=a.get("activityName") or (safe_get(a, "activityType", "typeKey") or "unknown"),
        duration_min=sec_to_min(a.get("duration")),
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
    for name in method_names:
        fn = getattr(client, name, None)
        if callable(fn):
            try:
                return fn(*args, **kwargs)
            except Exception:
                continue
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
    if aero >= 4 or anaer >= 2 or load >= 120:
        return "hoch"
    if aero >= 2 or anaer >= 0.7 or load >= 60:
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
    except Exception:
        pass
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


def history_window(history: Dict[str, Any], current_day: str, field: str, baseline_days: int) -> List[float]:
    days = history.get("days", {})
    current = datetime.strptime(current_day, "%Y-%m-%d").date()
    earliest = current - timedelta(days=baseline_days)
    vals = []
    for d, payload in days.items():
        try:
            day_date = datetime.strptime(d, "%Y-%m-%d").date()
        except Exception:
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
    std = max(std, 0.5)
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
) -> Dict[str, Any]:
    if not morning:
        return {"score": None, "bands": {}, "baselines": {}}

    fields = {
        "hrv": True,
        "resting_hr": False,
        "respiration": False,
        "sleep_h": True,
    }

    baselines: Dict[str, Any] = {}
    bands: Dict[str, str] = {}
    contributions: List[float] = []

    for field, higher_is_better in fields.items():
        vals = history_window(history, day_str, field, baseline_days)
        baseline, std = median_std(vals)
        current = getattr(morning, field)
        baselines[field] = {"baseline": baseline, "std": std, "n": len(vals)}
        bands[field] = band_text(current, baseline, std, higher_is_better)

        if current is not None and baseline is not None and std is not None:
            std_eff = max(std, 0.5)
            z = (current - baseline) / std_eff
            if not higher_is_better:
                z = -z
            z = max(-2.5, min(2.5, z))
            contributions.append(z)

    if not contributions:
        return {"score": None, "bands": bands, "baselines": baselines}

    avg_z = sum(contributions) / len(contributions)
    score = round(50 + avg_z * 15)
    score = max(1, min(99, score))
    return {"score": score, "bands": bands, "baselines": baselines}


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


def compute_load_metrics(history: Dict[str, Any], day_str: str) -> Dict[str, Optional[float]]:
    acute_7d = rolling_load(history, day_str, 7)
    chronic_28d = rolling_load(history, day_str, 28)

    acute_daily_avg = acute_7d / 7.0 if acute_7d > 0 else 0.0
    chronic_daily_avg = chronic_28d / 28.0 if chronic_28d > 0 else 0.0

    ratio = None
    if chronic_daily_avg > 0:
        ratio = round(acute_daily_avg / chronic_daily_avg, 2)

    return {
        "load_7d": round(acute_7d, 1),
        "load_28d": round(chronic_28d, 1),
        "load_7d_daily_avg": round(acute_daily_avg, 1),
        "load_28d_daily_avg": round(chronic_daily_avg, 1),
        "load_ratio": ratio,
    }


def load_ratio_label(ratio: Optional[float]) -> str:
    if ratio is None:
        return "-"
    if ratio < 0.8:
        return "unter Soll"
    if ratio <= 1.3:
        return "im Zielbereich"
    if ratio <= 1.5:
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

    if morning:
        if (
            (morning.respiration is not None and morning.respiration >= 15.5)
            or (morning.hrv is not None and morning.hrv <= 33)
            or (morning.resting_hr is not None and morning.resting_hr >= 58)
        ):
            return "Nur aktive Erholung / Z1-Z2 locker / Mobility"

    if ratio is not None and ratio > 1.5:
        return "Belastung aktuell zu hoch: nur locker / Erholung / Mobility"

    if not isinstance(score, int):
        return "Training nach Gefühl, Datenlage noch zu dünn"

    if mode == "run":
        if score <= 35:
            return "Nur locker laufen / Mobility"
        if score <= 50:
            return "Lockerer bis aerober Dauerlauf"
        if score <= 65:
            return "Moderater Lauf, keine harten Intervalle"
        if score <= 80:
            return "Qualitätstag Run möglich"
        return "Harter Lauf-Qualitätstag gut vertretbar"

    if mode == "bike":
        if score <= 35:
            return "Nur locker rollen / Mobility"
        if score <= 50:
            return "Lockere bis moderate Radeinheit"
        if score <= 65:
            return "Moderater Bike-Tag, keine maximalen Intervalle"
        if score <= 80:
            return "Qualitätstag Bike möglich"
        return "Harter Bike-Intervalltag gut vertretbar"

    if mode == "strength":
        if score <= 35:
            return "Nur Mobility oder sehr leichtes Krafttraining"
        if score <= 50:
            return "Moderates Krafttraining"
        if score <= 65:
            return "Normales Krafttraining möglich"
        if score <= 80:
            return "Schweres Krafttraining möglich"
        return "Schweres Krafttraining sehr gut vertretbar"

    if score <= 35:
        return "Nur locker / Erholung / Mobility"
    if score <= 50:
        return "Aerober Basistag oder moderates Krafttraining"
    if score <= 65:
        return "Solider Trainingstag: moderat bis zügig, aber nicht maximal"
    if score <= 80:
        return "Qualitätstag möglich"
    return "Harter Qualitätstag gut vertretbar"


def suggested_units(score: Optional[int], ratio: Optional[float], mode: str) -> List[str]:
    if score is None:
        return [
            "Datenlage zu dünn: 30-45 min locker nach Gefühl",
            "Optional 10-15 min Mobility",
        ]

    if ratio is not None and ratio > 1.5:
        return [
            "30-45 min sehr locker in Z1",
            "oder 20-30 min Mobility / Spazieren",
            "keine harte Qualität, kein schweres Krafttraining",
        ]

    if mode == "run":
        if score < 40:
            return [
                "30-40 min locker laufen oder gehen",
                "optional 6 x 20 s lockere Steigerungen nur wenn Beine gut",
            ]
        if score < 65:
            return [
                "45-60 min lockerer bis moderater Dauerlauf",
                "alternativ 30-45 min locker + 6 x 20 s Steigerungen",
            ]
        if score < 80:
            return [
                "6 x 3 min zügig mit 2 min locker",
                "alternativ 4 x 5 min an Schwelle mit 2-3 min locker",
            ]
        return [
            "5 x 4 min hart mit 3 min locker",
            "alternativ 8 x 400 m zügig mit lockerer Trabpause",
        ]

    if mode == "bike":
        if score < 40:
            return [
                "45-60 min sehr locker rollen in Z1/Z2",
                "hohe Kadenz, keine Intervalle",
            ]
        if score < 65:
            return [
                "60-90 min locker bis moderat in Z2",
                "alternativ 3 x 8 min Sweet Spot kontrolliert",
            ]
        if score < 80:
            return [
                "4 x 8 min zügig mit 4 min locker",
                "alternativ 5 x 5 min hart mit 3 min locker",
            ]
        return [
            "6 x 4 min VO2 mit 4 min locker",
            "alternativ 3 x 12 min Schwelle mit 6 min locker",
        ]

    if mode == "strength":
        if score < 40:
            return [
                "Nur Mobility, Technik oder sehr leichte Maschinenrunde",
                "kein schweres Beintraining",
            ]
        if score < 60:
            return [
                "Moderates Krafttraining Ganzkörper, 2-3 Sätze",
                "1-3 Wiederholungen im Tank lassen",
            ]
        if score < 80:
            return [
                "Schweres Krafttraining möglich, Hauptlifts fokussieren",
                "z. B. 3-5 Sätze Grundübungen, moderates Volumen",
            ]
        return [
            "Schwerer Krafttag gut vertretbar",
            "z. B. Hauptübungen schwer + 1-2 Zusatzübungen",
        ]

    # hybrid = run + bike + strength
    if score < 40:
        return [
            "Run/Bike: 30-40 min locker",
            "Mobility: 20-30 min",
            "Strength: nur leichtes Krafttraining ohne schwere Sätze",
        ]
    if score < 60:
        return [
            "Run: 45-60 min locker bis moderat",
            "Bike: 60-90 min locker Z2",
            "Strength: normale eGym-Runde / moderates Ganzkörpertraining",
        ]
    if score < 80:
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
    if ratio is not None and ratio > 1.5:
        return flags

    if mode == "run":
        if score >= 65:
            flags["quality"] = "JA"
        if score >= 80:
            flags["max_test"] = "JA"
        if score >= 55:
            flags["strength_heavy"] = "JA"
        return flags

    if mode == "bike":
        if score >= 65:
            flags["quality"] = "JA"
        if score >= 82:
            flags["max_test"] = "JA"
        if score >= 55:
            flags["strength_heavy"] = "JA"
        return flags

    if mode == "strength":
        if score >= 55:
            flags["strength_heavy"] = "JA"
        if score >= 70:
            flags["quality"] = "JA"
        if score >= 85:
            flags["max_test"] = "JA"
        return flags

    if score >= 60:
        flags["quality"] = "JA"
    if score >= 60:
        flags["strength_heavy"] = "JA"
    if score >= 82:
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
            except Exception:
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
        load_metrics["load_ratio_label"] = load_ratio_label(load_metrics.get("load_ratio"))
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
    
def main_logic(mode: str = "hybrid") -> dict:
    """
    Vercel-tauglicher Einstieg für das Dashboard.
    Holt heutige Daten, berechnet Empfehlung und gibt JSON zurück.
    Speichert nichts auf das lokale Dateisystem.
    """
    client = load_client()
    history = load_history(DEFAULT_HISTORY_PATH)

    recent_activities = get_recent_activities(client, 400)
    today_str = date.today().isoformat()

    activities_today = [a for a in recent_activities if a.date_local == today_str]

    morning = None
    if True:
        try:
            morning, _bundle = fetch_morning_metrics(client, today_str)
        except Exception:
            morning = None

    summary = aggregate_day(activities_today)
    update_history(history, today_str, morning, summary)

    readiness = compute_readiness(morning, history, today_str, 21)
    load_metrics = compute_load_metrics(history, today_str)
    load_metrics["load_ratio_label"] = load_ratio_label(load_metrics.get("load_ratio"))
    load_metrics["readiness_score"] = readiness.get("score")

    trained_today = has_training_today(recent_activities, today_str)
    recommendation_day = infer_target_day(today_str, morning is not None, trained_today)

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
        today_day=today_str,
        latest_morning=morning,
        today_summary=summary,
        today_load_metrics=load_metrics,
        today_activities=activities_today,
        dashboard_recommendations=recs,
        units=units.get(mode, units["hybrid"]),
    )

    return {
        "date": today_str,
        "recommendation_day": recommendation_day,
        "mode": mode,
        "morning": asdict(morning) if morning else None,
        "activities": [asdict(a) for a in activities_today],
        "summary": summary,
        "readiness": readiness,
        "load_metrics": load_metrics,
        "recommendations": recs,
        "units": units,
        "ai_prompt": ai_prompt,
    }

if __name__ == "__main__":
    raise SystemExit(main())
