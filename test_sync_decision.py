from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from backend.services.sync_decision import SyncPolicy, build_sync_status_response, decide_sync_action


class SyncDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        self.policy = SyncPolicy(
            freshness_threshold_hours=6,
            stale_threshold_hours=12,
            backfill_threshold_days=3,
            auto_backfill_limit_days=3,
            lock_ttl_seconds=600,
            auto_poll_seconds=5,
        )

    def test_auto_sync_uses_update_for_stale_recent_gap(self):
        status = self._status(last_success_hours_ago=8)
        needs = self._needs(missing_days=1, missing_recent_day=True, has_credentials=True)

        decision = decide_sync_action(
            status,
            self.now,
            needs,
            trigger_source="auto",
            requested_mode="auto",
            policy=self.policy,
        )

        self.assertTrue(decision["should_start"])
        self.assertEqual("update", decision["mode"])
        self.assertEqual("missing_recent_day", decision["reason"])

    def test_auto_sync_uses_backfill_for_small_stale_gap(self):
        status = self._status(last_success_hours_ago=10)
        needs = self._needs(missing_days=3, missing_recent_day=True, has_credentials=True)

        decision = decide_sync_action(
            status,
            self.now,
            needs,
            trigger_source="auto",
            requested_mode="auto",
            policy=self.policy,
        )

        self.assertTrue(decision["should_start"])
        self.assertEqual("backfill", decision["mode"])
        self.assertEqual("gap_detected", decision["reason"])

    def test_auto_sync_uses_update_for_large_gap_and_sets_backfill_recommendation(self):
        status = self._status(last_success_hours_ago=10)
        needs = self._needs(missing_days=10, missing_recent_day=True, has_credentials=True)

        decision = decide_sync_action(
            status,
            self.now,
            needs,
            trigger_source="auto",
            requested_mode="auto",
            policy=self.policy,
        )
        response = build_sync_status_response(status, needs, now=self.now, policy=self.policy)

        self.assertTrue(decision["should_start"])
        self.assertEqual("update", decision["mode"])
        self.assertEqual("missing_recent_day", decision["reason"])
        self.assertTrue(response["backfillRecommended"])

    def test_auto_sync_skips_when_fresh_even_with_small_gap(self):
        status = self._status(last_success_hours_ago=2)
        needs = self._needs(missing_days=6, missing_recent_day=False, has_credentials=True)

        decision = decide_sync_action(
            status,
            self.now,
            needs,
            trigger_source="auto",
            requested_mode="auto",
            policy=self.policy,
        )

        self.assertFalse(decision["should_start"])
        self.assertEqual("fresh_no_action", decision["reason"])

    def test_missing_credentials_blocks_auto_sync(self):
        status = self._status(last_success_hours_ago=None)
        needs = self._needs(missing_days=28, missing_recent_day=True, has_credentials=False)

        decision = decide_sync_action(
            status,
            self.now,
            needs,
            trigger_source="auto",
            requested_mode="auto",
            policy=self.policy,
        )
        response = build_sync_status_response(status, needs, now=self.now, policy=self.policy)

        self.assertFalse(decision["should_start"])
        self.assertEqual("credentials_missing", decision["reason"])
        self.assertEqual("blocked", response["syncState"])
        self.assertFalse(response["canStartSync"])

    def test_manual_update_allowed_when_fresh(self):
        status = self._status(last_success_hours_ago=1)
        needs = self._needs(missing_days=0, missing_recent_day=False, has_credentials=True)

        decision = decide_sync_action(
            status,
            self.now,
            needs,
            trigger_source="manual",
            requested_mode="update",
            policy=self.policy,
        )

        self.assertTrue(decision["should_start"])
        self.assertEqual("manual_request", decision["reason"])

    def test_auth_error_remains_blocked(self):
        status = self._status(last_success_hours_ago=24, sync_state="blocked", last_error_category="auth")
        needs = self._needs(missing_days=4, missing_recent_day=True, has_credentials=True)

        decision = decide_sync_action(
            status,
            self.now,
            needs,
            trigger_source="auto",
            requested_mode="auto",
            policy=self.policy,
        )
        response = build_sync_status_response(status, needs, now=self.now, policy=self.policy)

        self.assertFalse(decision["should_start"])
        self.assertEqual("credentials_invalid", decision["reason"])
        self.assertEqual("blocked", response["syncState"])

    def test_transient_cooldown_keeps_error_state_and_disables_actions(self):
        status = self._status(
            last_success_hours_ago=24,
            sync_state="error",
            last_error_category="transient",
            cooldown_minutes=15,
        )
        needs = self._needs(missing_days=2, missing_recent_day=True, has_credentials=True)

        decision = decide_sync_action(
            status,
            self.now,
            needs,
            trigger_source="auto",
            requested_mode="auto",
            policy=self.policy,
        )
        response = build_sync_status_response(status, needs, now=self.now, policy=self.policy)

        self.assertFalse(decision["should_start"])
        self.assertEqual("cooldown_active", decision["reason"])
        self.assertEqual("error", response["syncState"])
        self.assertFalse(response["canStartSync"])

    def _status(
        self,
        *,
        last_success_hours_ago: int | None,
        sync_state: str = "success",
        last_error_category: str | None = None,
        cooldown_minutes: int | None = None,
    ) -> dict:
        last_successful_sync_at = None
        if last_success_hours_ago is not None:
            last_successful_sync_at = (self.now - timedelta(hours=last_success_hours_ago)).isoformat()
        cooldown_until = None
        if cooldown_minutes is not None:
            cooldown_until = (self.now + timedelta(minutes=cooldown_minutes)).isoformat()
        return {
            "sync_state": sync_state,
            "sync_mode": "update",
            "last_successful_sync_at": last_successful_sync_at,
            "last_attempted_sync_at": last_successful_sync_at,
            "last_started_sync_at": last_successful_sync_at,
            "last_finished_sync_at": last_successful_sync_at,
            "last_error_category": last_error_category,
            "last_error_code": None,
            "last_error_message": None,
            "cooldown_until": cooldown_until,
            "auto_sync_enabled": True,
            "baseline_rebuild_recommended": False,
            "lock_token": None,
            "lock_expires_at": None,
            "stale_score": 0,
        }

    @staticmethod
    def _needs(*, missing_days: int, missing_recent_day: bool, has_credentials: bool) -> dict:
        return {
            "missingDaysCount": missing_days,
            "missingRecentDay": missing_recent_day,
            "hasCredentials": has_credentials,
        }


if __name__ == "__main__":
    unittest.main()
