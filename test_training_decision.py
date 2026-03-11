from __future__ import annotations

import unittest

from backend.services.baseline_service import normalized_metric_deviation
from backend.services.training_decision import compute_training_decision, compute_recovery_layer


class TrainingDecisionLogicTests(unittest.TestCase):
    def test_recovery_layer_keeps_small_positive_baseline_shifts_conservative(self):
        recovery = compute_recovery_layer(
            today={
                "readiness": 74,
                "hrv": 52.5,
                "restingHr": 48,
                "sleepHours": 7.5,
                "respiration": 14.2,
            },
            baseline={
                "hrv": 50.0,
                "restingHr": 50.0,
                "sleepHours": 7.0,
                "respiration": 14.0,
            },
        )

        self.assertEqual(recovery["status"], "Borderline")
        self.assertAlmostEqual(recovery["score"], 0.07, places=2)

    def test_baseline_metric_scoring_penalizes_negative_shifts_more_than_it_rewards_positive_shifts(self):
        resting_hr_better = normalized_metric_deviation("restingHr", 46, 50)
        resting_hr_worse = normalized_metric_deviation("restingHr", 54, 50)
        sleep_better = normalized_metric_deviation("sleepHours", 8.0, 7.0)
        sleep_worse = normalized_metric_deviation("sleepHours", 6.0, 7.0)

        self.assertGreater(resting_hr_better, 0)
        self.assertLess(resting_hr_worse, 0)
        self.assertGreater(abs(resting_hr_worse), resting_hr_better)
        self.assertGreater(sleep_better, 0)
        self.assertLess(sleep_worse, 0)
        self.assertGreater(abs(sleep_worse), sleep_better)

    def test_decision_why_lines_use_semantic_reasons_instead_of_raw_metric_debug_copy(self):
        decision = compute_training_decision(
            {
                "mode": "hybrid",
                "today": {
                    "readiness": 58,
                    "hrv": 44,
                    "restingHr": 54,
                    "sleepHours": 6.0,
                    "respiration": 15.1,
                },
                "baseline": {
                    "hrv": 50,
                    "restingHr": 50,
                    "sleepHours": 7.0,
                    "respiration": 14.0,
                },
                "comparisons": {
                    "hrvDeltaPct": -12.0,
                    "restingHrDeltaPct": 8.0,
                    "restingHrDeltaBpm": 4.0,
                    "sleepDeltaPct": -14.3,
                    "sleepDeltaHours": -1.0,
                    "respirationDeltaPct": 7.9,
                    "respirationDeltaBrpm": 1.1,
                },
                "load": {
                    "ratio7to28": 1.22,
                    "hardSessionsLast3d": 1,
                    "hardSessionsLast7d": 1,
                    "yesterdaySessionType": "easy",
                    "veryHighYesterdayLoad": False,
                },
            }
        )

        self.assertGreaterEqual(len(decision["why"]), 3)
        self.assertEqual(decision["why"][0], "Recovery suppressed")
        self.assertEqual(decision["why"][1], "Load reduced")
        self.assertIn("Intensity capped at recovery only", decision["why"])
        self.assertTrue(all("%" not in line for line in decision["why"]))


if __name__ == "__main__":
    unittest.main()
