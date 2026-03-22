from __future__ import annotations

import unittest

from backend.services.training_decision import compute_training_decision


class ModeFilteringTests(unittest.TestCase):
    """Tests für die Modus-Filterung der Session-Empfehlungen."""

    def _create_payload(self, mode: str) -> dict:
        """Erstellt ein Test-Payload mit gegebenem Modus."""
        return {
            "mode": mode,
            "today": {
                "readiness": 75,
                "hrv": 55,
                "restingHr": 48,
                "sleepHours": 7.5,
                "respiration": 14.0,
            },
            "baseline": {
                "hrv": 50,
                "restingHr": 50,
                "sleepHours": 7.0,
                "respiration": 14.0,
            },
            "comparisons": {
                "hrvDeltaPct": 10.0,
                "restingHrDeltaPct": -4.0,
                "restingHrDeltaBpm": -2.0,
                "sleepDeltaPct": 7.1,
                "sleepDeltaHours": 0.5,
                "respirationDeltaPct": 0.0,
                "respirationDeltaBrpm": 0.0,
            },
            "load": {
                "ratio7to28": 0.95,
                "hardSessionsLast3d": 0,
                "hardSessionsLast7d": 1,
                "yesterdaySessionType": "easy",
                "veryHighYesterdayLoad": False,
            },
        }

    def test_run_mode_only_shows_run_sessions(self):
        """Wenn Modus 'run' ist, sollten nur Run-Sessions angezeigt werden."""
        decision = compute_training_decision(self._create_payload("run"))
        
        # Alle best_options sollten den sportTag 'run' haben
        for option in decision["bestOptions"]:
            self.assertEqual(
                option["sportTag"], 
                "run",
                f"Session '{option['label']}' hat sportTag '{option['sportTag']}' statt 'run'"
            )
        
        # Es sollte 3 Optionen geben
        self.assertEqual(len(decision["bestOptions"]), 3)
        
        # Die Optionen sollten unterschiedliche Intensitätsstufen haben
        intensity_levels = [opt.get("intensityLevel") for opt in decision["bestOptions"]]
        self.assertEqual(len(set(intensity_levels)), 3, "Die 3 Optionen sollten unterschiedliche Intensitätsstufen haben")
        
        # Jede Option sollte eine Farbe haben
        for option in decision["bestOptions"]:
            self.assertIn("color", option, "Jede Option sollte eine Farbe haben")
            self.assertIn(option["color"], ["green", "yellow", "orange", "red"], "Farbe sollte gültig sein")

    def test_bike_mode_only_shows_bike_sessions(self):
        """Wenn Modus 'bike' ist, sollten nur Bike-Sessions angezeigt werden."""
        decision = compute_training_decision(self._create_payload("bike"))
        
        # Alle best_options sollten den sportTag 'bike' haben
        for option in decision["bestOptions"]:
            self.assertEqual(
                option["sportTag"], 
                "bike",
                f"Session '{option['label']}' hat sportTag '{option['sportTag']}' statt 'bike'"
            )

    def test_strength_mode_only_shows_strength_sessions(self):
        """Wenn Modus 'strength' ist, sollten nur Strength-Sessions angezeigt werden."""
        decision = compute_training_decision(self._create_payload("strength"))
        
        # Alle best_options sollten den sportTag 'strength' haben
        for option in decision["bestOptions"]:
            self.assertEqual(
                option["sportTag"], 
                "strength",
                f"Session '{option['label']}' hat sportTag '{option['sportTag']}' statt 'strength'"
            )

    def test_hybrid_mode_shows_mixed_sessions(self):
        """Wenn Modus 'hybrid' ist, können verschiedene Sportarten angezeigt werden."""
        decision = compute_training_decision(self._create_payload("hybrid"))
        
        # Bei hybrid können verschiedene Sportarten vorkommen
        sport_tags = {option["sportTag"] for option in decision["bestOptions"]}
        # Mindestens eine Sportart sollte vorhanden sein
        self.assertGreater(len(sport_tags), 0)


if __name__ == "__main__":
    unittest.main()