from __future__ import annotations

from typing import Any, Dict, List


def build_tomorrow_impacts(
    recovery_score: float,
    hard_sessions_last_3d: int,
    best_options: List[Dict[str, Any]],
) -> Dict[str, Any]:
    by_session_type: Dict[str, Dict[str, Any]] = {}
    summary: Dict[str, str] = {}

    for index, option in enumerate(best_options, start=1):
        impact = project_tomorrow_effect(
            recovery_score=recovery_score,
            fatigue_cost=float(option.get("fatigueCost") or 0.0),
            hard_sessions_last_3d=hard_sessions_last_3d,
        )
        by_session_type[option["type"]] = impact
        summary[f"ifBestOption{index}"] = impact["text"]

    return {
        **summary,
        "bySessionType": by_session_type,
    }


def project_tomorrow_effect(
    *,
    recovery_score: float,
    fatigue_cost: float,
    hard_sessions_last_3d: int,
) -> Dict[str, Any]:
    penalty = intensity_density_penalty(hard_sessions_last_3d)
    predicted_score = round(float(recovery_score) - fatigue_cost - penalty, 2)

    if predicted_score > 0.15:
        return {
            "predictedScore": predicted_score,
            "outlook": "quality session possible",
            "tone": "positive",
            "text": "Tomorrow's window can support a quality session.",
            "windowLabel": "Best fit for tomorrow: quality work.",
        }
    if predicted_score >= -0.10:
        return {
            "predictedScore": predicted_score,
            "outlook": "controlled training fits best",
            "tone": "warning",
            "text": "Tomorrow looks better for controlled work than for another hard day.",
            "windowLabel": "Best fit for tomorrow: controlled aerobic work.",
        }
    return {
        "predictedScore": predicted_score,
        "outlook": "easy training fits best",
        "tone": "critical",
        "text": "Tomorrow looks better for easy or recovery work.",
        "windowLabel": "Best fit for tomorrow: easy or recovery work.",
    }


def intensity_density_penalty(hard_sessions_last_3d: int) -> float:
    if hard_sessions_last_3d <= 0:
        return 0.0
    if hard_sessions_last_3d == 1:
        return 0.1
    return 0.2
