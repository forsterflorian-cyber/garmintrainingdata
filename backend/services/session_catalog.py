from __future__ import annotations

from typing import Any, Dict, List


SESSION_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "recovery": [
        {
            "id": "walk_mobility",
            "label": "Walk / Mobility",
            "details": "20-40 min walk plus 10-15 min mobility",
            "sportTag": "recovery",
            "fatigueCost": 0.1,
        },
        {
            "id": "easy_spin",
            "label": "Easy Spin",
            "details": "30-45 min very easy bike, all Z1",
            "sportTag": "bike",
            "fatigueCost": 0.2,
        },
        {
            "id": "no_structured_intensity",
            "label": "No Structured Intensity",
            "details": "Keep the day unstructured and light",
            "sportTag": "recovery",
            "fatigueCost": 0.1,
        },
    ],
    "easy": [
        {
            "id": "easy_run",
            "label": "Easy Run",
            "details": "30-45 min easy aerobic, conversational only",
            "sportTag": "run",
            "fatigueCost": 0.2,
        },
        {
            "id": "easy_ride",
            "label": "Easy Ride",
            "details": "45-60 min smooth Z1/Z2 ride",
            "sportTag": "bike",
            "fatigueCost": 0.2,
        },
        {
            "id": "strength_light",
            "label": "Mobility / Strength Light",
            "details": "20-30 min light accessory or mobility only",
            "sportTag": "strength",
            "fatigueCost": 0.2,
        },
    ],
    "moderate": [
        {
            "id": "moderate_run",
            "label": "Moderate Run",
            "details": "45-70 min controlled aerobic endurance",
            "sportTag": "run",
            "fatigueCost": 0.4,
        },
        {
            "id": "moderate_ride",
            "label": "Moderate Ride",
            "details": "60-90 min Z2 with only low Z3 exposure",
            "sportTag": "bike",
            "fatigueCost": 0.4,
        },
        {
            "id": "strength_maintenance",
            "label": "Strength Maintenance",
            "details": "2-3 controlled full-body rounds, no grinding",
            "sportTag": "strength",
            "fatigueCost": 0.3,
        },
    ],
    "threshold": [
        {
            "id": "threshold_run",
            "label": "Threshold Run",
            "details": "2 x 10-15 min around LT with full control",
            "sportTag": "run",
            "fatigueCost": 0.7,
        },
        {
            "id": "threshold_ride",
            "label": "Threshold Ride",
            "details": "2 x 12 min around FTP",
            "sportTag": "bike",
            "fatigueCost": 0.7,
        },
        {
            "id": "moderate_endurance",
            "label": "Moderate Endurance",
            "details": "45-75 min controlled aerobic work",
            "sportTag": "hybrid",
            "fatigueCost": 0.4,
        },
    ],
    "vo2": [
        {
            "id": "vo2_run",
            "label": "VO2 Run",
            "details": "5 x 3 min @ VO2 pace",
            "sportTag": "run",
            "fatigueCost": 0.9,
        },
        {
            "id": "vo2_ride",
            "label": "VO2 Ride",
            "details": "6 x 2 min @ 120% FTP",
            "sportTag": "bike",
            "fatigueCost": 0.9,
        },
        {
            "id": "threshold_alternative",
            "label": "Threshold Alternative",
            "details": "Run 2 x 10 min or Bike 2 x 12 min steady threshold",
            "sportTag": "hybrid",
            "fatigueCost": 0.7,
        },
    ],
    "strength": [
        {
            "id": "strength_hypertrophy",
            "label": "Strength Hypertrophy",
            "details": "3-4 main sets, stop 1-2 reps before failure",
            "sportTag": "strength",
            "fatigueCost": 0.6,
        },
        {
            "id": "strength_maintenance",
            "label": "Strength Maintenance",
            "details": "2-3 rounds, low soreness target",
            "sportTag": "strength",
            "fatigueCost": 0.3,
        },
    ],
}


SESSION_INDEX: Dict[str, Dict[str, Any]] = {
    session["id"]: session
    for sessions in SESSION_CATALOG.values()
    for session in sessions
}


def fatigue_label(cost: float) -> str:
    if cost >= 0.8:
        return "high"
    if cost >= 0.5:
        return "moderate-high"
    if cost >= 0.3:
        return "moderate"
    return "low"


def get_session(session_id: str) -> Dict[str, Any]:
    session = SESSION_INDEX[session_id]
    return {
        **session,
        "fatigueLabel": fatigue_label(float(session["fatigueCost"])),
    }
