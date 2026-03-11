from __future__ import annotations

import sys
import types
import unittest

fake_garminconnect = types.ModuleType("garminconnect")
fake_garminconnect.Garmin = object
sys.modules.setdefault("garminconnect", fake_garminconnect)

from dashboard_service import build_dashboard_payload, build_prompt_from_payload


class DashboardServiceHardeningTests(unittest.TestCase):
    def test_build_dashboard_payload_skips_malformed_rows_and_activity_entries(self):
        rows = [
            {"date": "not-a-date", "data": {"date": "not-a-date"}},
            {"date": "2026-03-09", "data": "broken"},
            {
                "date": "2026-03-10",
                "data": {
                    "date": "2026-03-10",
                    "morning": {
                        "hrv": "52.5",
                        "resting_hr": 48,
                        "sleep_h": 7.5,
                        "respiration": "14.2",
                    },
                    "readiness": {
                        "score": 74,
                        "baselines": {
                            "hrv": {"baseline": "50.0"},
                            "resting_hr": {"baseline": 50},
                            "sleep_h": {"baseline": "7.0"},
                            "respiration": {"baseline": 14},
                        },
                    },
                    "summary": {
                        "training_load_sum": "68.0",
                        "aero_te_sum": 3.2,
                        "anaer_te_sum": "0.6",
                    },
                    "load_metrics": {
                        "load_7d": "280.0",
                        "load_28d": 980.0,
                        "load_7d_daily_avg": 40.0,
                        "load_28d_daily_avg": "35.0",
                        "load_ratio": "1.02",
                        "load_ratio_label": "target",
                    },
                    "activities": [
                        {
                            "activity_id": 1,
                            "start_local": "2026-03-10 07:00",
                            "date_local": "2026-03-10",
                            "type_key": "running",
                            "name": "Morning Run",
                            "duration_min": 45,
                            "distance_km": 9.2,
                            "avg_hr": 146,
                            "max_hr": 171,
                            "avg_power": None,
                            "max_power": None,
                            "avg_speed_kmh": 12.3,
                            "pace_min_per_km": "4:52",
                            "aerobic_te": "3.1",
                            "anaerobic_te": 0.3,
                            "training_load": "72.0",
                        },
                        "broken",
                    ],
                    "recommendations": {"hybrid": "Moderate only"},
                    "units": {"hybrid": ["Easy aerobic 45 min"]},
                    "ai_prompt": "cached",
                },
            },
        ]

        payload = build_dashboard_payload(rows)

        self.assertEqual(payload["date"], "2026-03-10")
        self.assertEqual(payload["summary"]["days"], 1)
        self.assertEqual(len(payload["history"]["rows"]), 1)
        self.assertEqual(len(payload["detail"]["activities"]), 1)
        self.assertEqual(payload["load"]["ratio7to28"], 1.02)
        self.assertEqual(payload["decision"]["primaryRecommendation"], "Moderate only")
        self.assertTrue(all("%" not in line for line in payload["decision"]["why"]))
        self.assertEqual(payload["today"]["sessionType"], "threshold")
        self.assertEqual(payload["detail"]["sessionType"], "threshold")
        self.assertEqual(payload["history"]["rows"][0]["sessionType"], "threshold")
        self.assertEqual(payload["detail"]["activities"][0]["sport_tag"], "run")
        self.assertEqual(payload["detail"]["activities"][0]["sessionType"], "threshold")
        self.assertEqual(payload["reference"]["baselineDays"], 28)
        self.assertEqual(payload["reference"]["baselineSource"], "stored")

    def test_build_prompt_from_payload_tolerates_partial_activity_payloads(self):
        prompt = build_prompt_from_payload(
            {
                "date": "2026-03-10",
                "recommendation_day": "2026-03-11",
                "summary": {},
                "load_metrics": {"readiness_score": 70},
                "activities": [{"name": "Short Run"}, None, "broken"],
                "recommendations": {},
                "units": {"hybrid": ["Easy aerobic"]},
            },
            "hybrid",
        )

        self.assertIsInstance(prompt, str)
        self.assertIn("2026-03-11", prompt)
        self.assertIn("Short Run", prompt)

    def test_range_changes_the_trailing_baseline_reference_window(self):
        def row(day: str, hrv: int, stored_baseline: int) -> dict:
            return {
                "date": day,
                "data": {
                    "date": day,
                    "morning": {
                        "hrv": hrv,
                        "resting_hr": 50,
                        "sleep_h": 7.0,
                        "respiration": 14.0,
                    },
                    "readiness": {
                        "score": 70,
                        "baselines": {
                            "hrv": {"baseline": stored_baseline},
                            "resting_hr": {"baseline": 50},
                            "sleep_h": {"baseline": 7.0},
                            "respiration": {"baseline": 14.0},
                        },
                    },
                    "summary": {"training_load_sum": 20},
                    "load_metrics": {
                        "load_7d": 120,
                        "load_28d": 420,
                        "load_7d_daily_avg": 17.1,
                        "load_28d_daily_avg": 15.0,
                        "load_ratio": 1.14,
                    },
                    "activities": [],
                },
            }

        rows = [
            row("2026-03-01", 40, 32),
            row("2026-03-02", 50, 32),
            row("2026-03-03", 60, 32),
            row("2026-03-04", 70, 32),
            row("2026-03-05", 80, 32),
            row("2026-03-06", 90, 32),
        ]

        payload_4d = build_dashboard_payload(rows, selected_date="2026-03-06", period_days=4)
        payload_5d = build_dashboard_payload(rows, selected_date="2026-03-06", period_days=5)

        self.assertEqual(payload_4d["baseline"]["hrv"], 65.0)
        self.assertEqual(payload_5d["baseline"]["hrv"], 60.0)
        self.assertEqual(payload_4d["reference"]["baselineSource"], "rolling")
        self.assertEqual(payload_5d["reference"]["baselineSource"], "rolling")
        self.assertEqual(payload_4d["history"]["rows"][0]["date"], "2026-03-03")
        self.assertEqual(payload_5d["history"]["rows"][0]["date"], "2026-03-02")


if __name__ == "__main__":
    unittest.main()
