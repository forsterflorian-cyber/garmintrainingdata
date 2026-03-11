from __future__ import annotations

import sys
import types
import unittest
from datetime import date, timedelta
from unittest.mock import patch

fake_garminconnect = types.ModuleType("garminconnect")
fake_garminconnect.Garmin = object
sys.modules.setdefault("garminconnect", fake_garminconnect)

fake_crypto_utils = types.ModuleType("crypto_utils")
fake_crypto_utils.encrypt = lambda value: value
fake_crypto_utils.decrypt = lambda value: value
sys.modules.setdefault("crypto_utils", fake_crypto_utils)

from backend.services.sync_decision import SyncPolicy
from backend.services.sync_runner import SyncRunner


class FakeStore:
    def fetch_account(self, _user_id: str):
        return None


class CaptureSyncRunner(SyncRunner):
    def __init__(self, *, policy: SyncPolicy):
        super().__init__(supabase_client=object(), session_store=FakeStore(), policy=policy)
        self.captured_targets: list[str] = []

    def _sync_days(self, user_id: str, *, lock_token: str, target_days: list[str]):
        self.captured_targets = list(target_days)
        latest = max(target_days) if target_days else None
        return len(target_days), len(target_days), latest


class SyncRunnerWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = SyncPolicy(
            initial_backfill_days=180,
            missing_days_window_days=180,
            incremental_sync_days=3,
            incremental_gap_fill_days=3,
        )

    def test_backfill_defaults_to_full_180_day_window(self):
        runner = CaptureSyncRunner(policy=self.policy)

        with patch("backend.services.sync_runner.fetch_training_rows", return_value=[]):
            runner._run_backfill_sync_blocking("user-1", lock_token="lock", days=None)

        self.assertEqual(len(runner.captured_targets), 180)
        self.assertEqual(runner.captured_targets[-1], date.today().isoformat())
        self.assertEqual(runner.captured_targets[0], (date.today() - timedelta(days=179)).isoformat())

    def test_incremental_update_also_pulls_missing_days(self):
        runner = CaptureSyncRunner(policy=self.policy)
        gap_day = (date.today() - timedelta(days=30)).isoformat()
        rows = [
            {"date": (date.today() - timedelta(days=offset)).isoformat()}
            for offset in range(180)
            if (date.today() - timedelta(days=offset)).isoformat() != gap_day
        ]

        with patch("backend.services.sync_runner.fetch_training_rows", return_value=rows):
            runner._run_update_sync_blocking("user-1", lock_token="lock")

        recent_days = {
            (date.today() - timedelta(days=offset)).isoformat()
            for offset in range(self.policy.incremental_sync_days)
        }
        self.assertTrue(recent_days.issubset(set(runner.captured_targets)))
        self.assertIn(gap_day, runner.captured_targets)


if __name__ == "__main__":
    unittest.main()
