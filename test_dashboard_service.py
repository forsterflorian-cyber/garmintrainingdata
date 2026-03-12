from __future__ import annotations

import sys
import types
import unittest
from datetime import date, timedelta

fake_garminconnect = types.ModuleType("garminconnect")
fake_garminconnect.Garmin = object
sys.modules.setdefault("garminconnect", fake_garminconnect)

from dashboard_service import build_dashboard_payload, build_prompt_from_payload


def build_training_row(
    day: str,
    *,
    load_day: float | None = 20.0,
    load_7d: float | None = None,
    load_28d: float | None = None,
) -> dict:
    load_ratio = round(load_7d / load_28d, 3) if load_7d not in (None, 0) and load_28d not in (None, 0) else None
    return {
        "date": day,
        "data": {
            "date": day,
            "morning": {
                "hrv": 55,
                "resting_hr": 49,
                "sleep_h": 7.4,
                "respiration": 14.1,
            },
            "readiness": {
                "score": 72,
                "baselines": {
                    "hrv": {"baseline": 52},
                    "resting_hr": {"baseline": 50},
                    "sleep_h": {"baseline": 7.0},
                    "respiration": {"baseline": 14.0},
                },
            },
            "summary": {"training_load_sum": load_day},
            "load_metrics": {
                "load_7d": load_7d,
                "load_28d": load_28d,
                "load_7d_daily_avg": round(load_7d / 7, 2) if load_7d is not None else None,
                "load_28d_daily_avg": round(load_28d / 28, 2) if load_28d is not None else None,
                "load_ratio": load_ratio,
            },
            "activities": [],
        },
    }


def build_load_history(start_day: str, daily_loads: list[float | None]) -> list[dict]:
    start_value = date.fromisoformat(start_day)
    rows = []
    for index, load_day in enumerate(daily_loads):
        current_day = (start_value + timedelta(days=index)).isoformat()
        current_window = daily_loads[max(0, index - 6):index + 1]
        current_values = [value for value in current_window if value is not None]
        load_7d = round(sum(current_values), 1) if len(current_values) == len(current_window) else None
        chronic_window = daily_loads[max(0, index - 27):index + 1]
        chronic_values = [value for value in chronic_window if value is not None]
        load_28d = round(sum(chronic_values), 1) if len(chronic_values) == len(chronic_window) else None
        rows.append(build_training_row(current_day, load_day=load_day, load_7d=load_7d, load_28d=load_28d))
    return rows


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

    def test_load_momentum_marks_rising_load(self):
        rows = build_load_history("2026-03-01", [10.0] * 7 + [12.0] * 7)

        payload = build_dashboard_payload(rows, selected_date="2026-03-14", period_days=14)

        self.assertEqual(payload["load"]["momentum"]["value"], 0.2)
        self.assertEqual(payload["load"]["momentum"]["label"], "Rising")
        self.assertEqual(payload["load"]["momentum"]["previous7dLoad"], 70.0)

    def test_load_momentum_marks_falling_load(self):
        rows = build_load_history("2026-03-01", [15.0] * 7 + [10.0] * 7)

        payload = build_dashboard_payload(rows, selected_date="2026-03-14", period_days=14)

        self.assertEqual(payload["load"]["momentum"]["value"], -0.333)
        self.assertEqual(payload["load"]["momentum"]["label"], "Falling")
        self.assertEqual(payload["load"]["momentum"]["previous7dLoad"], 105.0)

    def test_load_momentum_marks_stable_load(self):
        rows = build_load_history("2026-03-01", [10.0] * 7 + [10.5] * 7)

        payload = build_dashboard_payload(rows, selected_date="2026-03-14", period_days=14)

        self.assertEqual(payload["load"]["momentum"]["value"], 0.05)
        self.assertEqual(payload["load"]["momentum"]["label"], "Stable")

    def test_load_momentum_is_null_when_previous_window_missing(self):
        rows = build_load_history("2026-03-01", [10.0] * 13)

        payload = build_dashboard_payload(rows, selected_date="2026-03-13", period_days=13)

        self.assertIsNone(payload["load"]["momentum"]["value"])
        self.assertIsNone(payload["load"]["momentum"]["label"])

    def test_load_momentum_is_null_when_previous_window_is_zero(self):
        rows = build_load_history("2026-03-01", [0.0] * 7 + [10.0] * 7)

        payload = build_dashboard_payload(rows, selected_date="2026-03-14", period_days=14)

        self.assertIsNone(payload["load"]["momentum"]["value"])
        self.assertIsNone(payload["load"]["momentum"]["label"])
        self.assertEqual(payload["load"]["momentum"]["previous7dLoad"], 0.0)

    def test_load_channel_series_includes_daily_and_window_loads(self):
        rows = build_load_history("2026-03-01", [12.0, 18.0, 25.0])

        payload = build_dashboard_payload(rows, selected_date="2026-03-03", period_days=3)

        self.assertEqual(
            payload["trends"]["loadChannelSeries"],
            [
                {"date": "2026-03-01", "dailyLoad": 12.0, "load7d": 12.0, "load28d": 12.0},
                {"date": "2026-03-02", "dailyLoad": 18.0, "load7d": 30.0, "load28d": 30.0},
                {"date": "2026-03-03", "dailyLoad": 25.0, "load7d": 55.0, "load28d": 55.0},
            ],
        )

    def test_load_channel_series_preserves_sparse_values(self):
        rows = [
            build_training_row("2026-03-01", load_day=15.0, load_7d=15.0, load_28d=15.0),
            build_training_row("2026-03-02", load_day=None, load_7d=None, load_28d=15.0),
        ]

        payload = build_dashboard_payload(rows, selected_date="2026-03-02", period_days=2)

        self.assertEqual(
            payload["trends"]["loadChannelSeries"],
            [
                {"date": "2026-03-01", "dailyLoad": 15.0, "load7d": 15.0, "load28d": 15.0},
                {"date": "2026-03-02", "dailyLoad": None, "load7d": None, "load28d": 15.0},
            ],
        )

    def test_empty_history_keeps_channel_payload_safe(self):
        payload = build_dashboard_payload([], selected_date="2026-03-14")

        self.assertEqual(payload["trends"]["loadChannelSeries"], [])
        self.assertIsNone(payload["load"]["momentum"]["value"])
        self.assertIsNone(payload["load"]["momentum"]["label"])
        self.assertEqual(payload["detail"]["activeDate"], "2026-03-14")
        self.assertEqual(payload["detail"]["activities"], [])
        self.assertEqual(payload["decision"]["why"], [])
        self.assertEqual(payload["baselineBars"], [])

    def test_partial_day_payload_keeps_missing_metrics_safe(self):
        rows = [
            {
                "date": "2026-03-14",
                "data": {
                    "date": "2026-03-14",
                    "morning": {},
                    "readiness": {},
                    "summary": {},
                    "load_metrics": {},
                    "activities": [None, {"type_key": "walking"}],
                },
            },
        ]

        payload = build_dashboard_payload(rows, selected_date="2026-03-14", period_days=7)

        self.assertEqual(payload["date"], "2026-03-14")
        self.assertEqual(len(payload["history"]["rows"]), 1)
        self.assertIsNone(payload["history"]["rows"][0]["readiness"])
        self.assertIsNone(payload["history"]["rows"][0]["ratio7to28"])
        self.assertEqual(payload["detail"]["activities"], [
            {
                "activity_id": None,
                "start_local": "",
                "date_local": "",
                "type_key": "walking",
                "name": "walking",
                "duration_min": None,
                "distance_km": None,
                "avg_hr": None,
                "max_hr": None,
                "avg_power": None,
                "max_power": None,
                "avg_speed_kmh": None,
                "pace_min_per_km": None,
                "aerobic_te": None,
                "anaerobic_te": None,
                "training_load": None,
                "sport_tag": "recovery",
                "sessionType": "recovery",
            },
        ])


if __name__ == "__main__":
    unittest.main()
