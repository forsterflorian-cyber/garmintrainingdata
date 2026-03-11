from __future__ import annotations

import unittest

from backend.services.app_flow_service import (
    APP_PHASE_DASHBOARD,
    APP_PHASE_GARMIN_SETUP,
    APP_PHASE_SETTINGS,
    GARMIN_STATE_ACTION_REQUIRED,
    GARMIN_STATE_MISSING,
    GARMIN_STATE_READY,
    build_authenticated_app_state,
)


class FakeGarminAccount:
    def __init__(self, *, has_email: bool = True, has_password: bool = True, credentials=("athlete@example.com", "secret")):
        self.user_id = "user-1"
        self.garmin_email_enc = "enc:email" if has_email else None
        self.garmin_password_enc = "enc:password" if has_password else None
        self._credentials = credentials

    def credentials(self):
        return self._credentials


class AppFlowServiceTests(unittest.TestCase):
    def test_missing_garmin_credentials_routes_to_onboarding(self):
        payload = build_authenticated_app_state(None, {"syncState": "blocked", "statusReason": "credentials_missing"})

        self.assertEqual(APP_PHASE_GARMIN_SETUP, payload["phase"])
        self.assertFalse(payload["dashboardAccessible"])
        self.assertEqual(GARMIN_STATE_MISSING, payload["garmin"]["connectionState"])
        self.assertTrue(payload["garmin"]["needsOnboarding"])
        self.assertFalse(payload["garmin"]["needsReconnect"])

    def test_blocked_garmin_connection_routes_to_settings(self):
        account = FakeGarminAccount()

        payload = build_authenticated_app_state(
            account,
            {
                "syncState": "blocked",
                "statusReason": "credentials_invalid",
                "lastErrorMessage": "Garmin sign-in failed. Check your Garmin email and password.",
            },
        )

        self.assertEqual(APP_PHASE_SETTINGS, payload["phase"])
        self.assertFalse(payload["dashboardAccessible"])
        self.assertEqual(GARMIN_STATE_ACTION_REQUIRED, payload["garmin"]["connectionState"])
        self.assertTrue(payload["garmin"]["isConfigured"])
        self.assertTrue(payload["garmin"]["needsReconnect"])

    def test_healthy_garmin_configuration_allows_dashboard(self):
        account = FakeGarminAccount()

        payload = build_authenticated_app_state(
            account,
            {
                "syncState": "fresh",
                "statusReason": "fresh_no_action",
            },
        )

        self.assertEqual(APP_PHASE_DASHBOARD, payload["phase"])
        self.assertTrue(payload["dashboardAccessible"])
        self.assertTrue(payload["settingsAccessible"])
        self.assertEqual(GARMIN_STATE_READY, payload["garmin"]["connectionState"])
        self.assertTrue(payload["garmin"]["isUsable"])

    def test_partial_garmin_storage_routes_to_settings(self):
        account = FakeGarminAccount(has_password=False)

        payload = build_authenticated_app_state(account, {"syncState": "blocked"})

        self.assertEqual(APP_PHASE_SETTINGS, payload["phase"])
        self.assertEqual(GARMIN_STATE_ACTION_REQUIRED, payload["garmin"]["connectionState"])
        self.assertFalse(payload["garmin"]["isConfigured"])
        self.assertTrue(payload["garmin"]["needsReconnect"])


if __name__ == "__main__":
    unittest.main()
