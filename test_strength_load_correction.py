from __future__ import annotations

import sys
import types
import unittest
from dataclasses import asdict
from datetime import date, timedelta

fake_garminconnect = types.ModuleType("garminconnect")
fake_garminconnect.Garmin = object
sys.modules.setdefault("garminconnect", fake_garminconnect)

from dashboard_service import build_dashboard_payload
from garmin_hybrid_report_v62_supabase_ready import (
    aggregate_day,
    compute_load_metrics,
    estimate_strength_load,
    is_strength_activity,
    load_ratio_label,
    summarize_activity,
    update_history,
)


def build_raw_activity(
    day: str,
    *,
    activity_id: int,
    type_key: str,
    name: str,
    duration_min: float | None,
    training_load: float | None,
) -> dict:
    return {
        "activityId": activity_id,
        "startTimeLocal": f"{day} 07:00:00",
        "activityType": {"typeKey": type_key},
        "activityName": name,
        "duration": int(duration_min * 60) if duration_min is not None else None,
        "trainingLoad": training_load,
    }


class StrengthLoadCorrectionTests(unittest.TestCase):
    def test_estimate_strength_load_scales_and_caps(self):
        self.assertEqual(estimate_strength_load(30), 24.0)
        self.assertEqual(estimate_strength_load(45), 36.0)
        self.assertEqual(estimate_strength_load(60), 48.0)
        self.assertEqual(estimate_strength_load(90), 60.0)
        self.assertIsNone(estimate_strength_load(None))
        self.assertIsNone(estimate_strength_load(0))

    def test_is_strength_activity_uses_type_and_name_fallbacks(self):
        self.assertTrue(
            is_strength_activity(
                {
                    "activityType": {"typeKey": "strength_training"},
                    "activityName": "Lower Body Session",
                }
            )
        )
        self.assertTrue(
            is_strength_activity(
                {
                    "activityType": {"typeKey": "workout"},
                    "activityName": "EGYM Training",
                }
            )
        )
        self.assertFalse(
            is_strength_activity(
                {
                    "activityType": {"typeKey": "workout"},
                    "activityName": "Indoor Bike",
                }
            )
        )

    def test_non_strength_activity_keeps_garmin_load(self):
        activity = summarize_activity(
            build_raw_activity(
                "2026-03-12",
                activity_id=1,
                type_key="running",
                name="Morning Run",
                duration_min=45,
                training_load=72,
            )
        )

        self.assertEqual(activity.training_load, 72.0)

    def test_strength_activity_uses_duration_floor_when_garmin_load_is_low(self):
        activity = summarize_activity(
            build_raw_activity(
                "2026-03-12",
                activity_id=2,
                type_key="strength_training",
                name="Leg Day",
                duration_min=45,
                training_load=8,
            )
        )

        self.assertEqual(activity.training_load, 36.0)

    def test_egym_training_name_fallback_applies_strength_load_floor(self):
        activity = summarize_activity(
            build_raw_activity(
                "2026-03-12",
                activity_id=22,
                type_key="workout",
                name="EGYM Training",
                duration_min=60,
                training_load=15,
            )
        )

        self.assertEqual(estimate_strength_load(60), 48.0)
        self.assertEqual(activity.training_load, 48.0)

    def test_indoor_bike_name_fallback_does_not_apply_strength_load_floor(self):
        activity = summarize_activity(
            build_raw_activity(
                "2026-03-12",
                activity_id=23,
                type_key="workout",
                name="Indoor Bike",
                duration_min=60,
                training_load=15,
            )
        )

        self.assertEqual(activity.training_load, 15.0)

    def test_strength_activity_keeps_higher_garmin_load(self):
        activity = summarize_activity(
            build_raw_activity(
                "2026-03-12",
                activity_id=3,
                type_key="strength_training",
                name="Heavy Strength",
                duration_min=45,
                training_load=52,
            )
        )

        self.assertEqual(activity.training_load, 52.0)

    def test_strength_correction_flows_through_daily_and_rolling_load_metrics(self):
        history = {"days": {}}
        rows = []
        start_day = date(2026, 3, 1)

        for offset in range(14):
            current_day = (start_day + timedelta(days=offset)).isoformat()
            if offset == 13:
                activity = summarize_activity(
                    build_raw_activity(
                        current_day,
                        activity_id=100 + offset,
                        type_key="strength_training",
                        name="Leg Day",
                        duration_min=45,
                        training_load=8,
                    )
                )
            else:
                activity = summarize_activity(
                    build_raw_activity(
                        current_day,
                        activity_id=100 + offset,
                        type_key="running",
                        name="Easy Run",
                        duration_min=40,
                        training_load=10,
                    )
                )

            summary = aggregate_day([activity])
            update_history(history, current_day, None, summary)
            load_metrics = compute_load_metrics(history, current_day)
            load_metrics["load_ratio_label"] = load_ratio_label(
                load_metrics.get("load_ratio"),
                load_metrics.get("load_ratio_reason"),
            )
            rows.append(
                {
                    "date": current_day,
                    "data": {
                        "date": current_day,
                        "morning": {},
                        "readiness": {},
                        "summary": summary,
                        "load_metrics": load_metrics,
                        "activities": [asdict(activity)],
                    },
                }
            )

        payload = build_dashboard_payload(rows, selected_date="2026-03-14", period_days=14)

        self.assertEqual(rows[-1]["data"]["summary"]["training_load_sum"], 36.0)
        self.assertEqual(rows[-1]["data"]["load_metrics"]["load_7d"], 96.0)
        self.assertEqual(rows[-1]["data"]["load_metrics"]["load_28d"], 166.0)
        self.assertEqual(rows[-1]["data"]["load_metrics"]["load_ratio"], 2.31)
        self.assertEqual(payload["trends"]["loadChannelSeries"][-1]["dailyLoad"], 36.0)
        self.assertEqual(payload["load"]["acute7d"], 96.0)
        self.assertEqual(payload["load"]["chronic28d"], 166.0)
        self.assertEqual(payload["load"]["ratio7to28"], 2.31)
        self.assertEqual(payload["load"]["momentum"]["current7dLoad"], 96.0)
        self.assertEqual(payload["load"]["momentum"]["previous7dLoad"], 70.0)
        self.assertEqual(payload["load"]["momentum"]["value"], 0.371)


if __name__ == "__main__":
    unittest.main()
