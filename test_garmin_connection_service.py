from __future__ import annotations

import sys
import types
import unittest
from dataclasses import dataclass

fake_crypto_utils = types.ModuleType("crypto_utils")
fake_crypto_utils.encrypt = lambda value: f"enc:{value}"
fake_crypto_utils.decrypt = lambda value: value.removeprefix("enc:")
sys.modules.setdefault("crypto_utils", fake_crypto_utils)

from backend.services.garmin_connection_service import (
    GARMIN_ACCOUNT_ALREADY_LINKED_MESSAGE,
    GarminConnectionService,
)
from observability import ServiceError


@dataclass
class FakeAccount:
    user_id: str
    garmin_account_key: str
    garmin_login_key: str
    garmin_account_key_source: str


class FakeStore:
    def __init__(self):
        self.rows = {}

    def find_conflicting_account(self, *, user_id: str, garmin_account_key: str | None, garmin_login_key: str | None):
        for owner_user_id, row in self.rows.items():
            if owner_user_id == user_id:
                continue
            if garmin_account_key and row.garmin_account_key == garmin_account_key:
                return row
            if garmin_login_key and row.garmin_login_key == garmin_login_key:
                return row
        return None

    def save_connected_account(
        self,
        user_id: str,
        email: str,
        password: str,
        session_payload: str,
        *,
        garmin_account_key: str | None = None,
        garmin_account_key_source: str | None = None,
        garmin_login_key: str | None = None,
    ):
        account = FakeAccount(
            user_id=user_id,
            garmin_account_key=garmin_account_key or "",
            garmin_login_key=garmin_login_key or "",
            garmin_account_key_source=garmin_account_key_source or "",
        )
        self.rows[user_id] = account
        return account


class FakeGarthClient:
    def __init__(self, profile):
        self.profile = profile


class FakeGarminClient:
    def __init__(self, profile):
        self.garth = FakeGarthClient(profile)
        self.display_name = profile.get("displayName")


class GarminConnectionServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.profiles = {
            "garmin-x@example.com": {
                "garminGuid": "guid-x",
                "profileId": 101,
                "id": 1001,
                "userName": "garmin-x-user",
                "displayName": "Garmin X",
            },
            "garmin-y@example.com": {
                "garminGuid": "guid-y",
                "profileId": 202,
                "id": 2002,
                "userName": "garmin-y-user",
                "displayName": "Garmin Y",
            },
        }
        self.service = GarminConnectionService(
            session_store=self.store,
            load_client_fn=self._load_client,
            export_session_fn=lambda _client: "session-json",
        )

    def _load_client(self, *, email: str, password: str):
        self.assertTrue(password)
        return FakeGarminClient(self.profiles[email])

    def test_user_a_can_connect_garmin_x(self):
        account = self.service.connect_account("user-a", email="garmin-x@example.com", password="secret")

        self.assertEqual("user-a", account.user_id)
        self.assertEqual("garmin_guid:guid-x", account.garmin_account_key)
        self.assertEqual("garmin_guid", account.garmin_account_key_source)
        self.assertEqual("garmin-x@example.com", account.garmin_login_key)

    def test_user_a_can_reconnect_same_garmin_account(self):
        self.service.connect_account("user-a", email="garmin-x@example.com", password="secret")

        account = self.service.connect_account("user-a", email="garmin-x@example.com", password="new-secret")

        self.assertEqual("user-a", account.user_id)
        self.assertEqual("garmin_guid:guid-x", account.garmin_account_key)
        self.assertEqual(1, len(self.store.rows))

    def test_user_b_is_blocked_when_garmin_x_is_already_owned_by_user_a(self):
        self.service.connect_account("user-a", email="garmin-x@example.com", password="secret")

        with self.assertRaises(ServiceError) as context:
            self.service.connect_account("user-b", email="garmin-x@example.com", password="secret")

        self.assertEqual(409, context.exception.status_code)
        self.assertEqual(GARMIN_ACCOUNT_ALREADY_LINKED_MESSAGE, context.exception.public_message)

    def test_user_b_can_connect_different_garmin_y(self):
        self.service.connect_account("user-a", email="garmin-x@example.com", password="secret")

        account = self.service.connect_account("user-b", email="garmin-y@example.com", password="secret")

        self.assertEqual("user-b", account.user_id)
        self.assertEqual("garmin_guid:guid-y", account.garmin_account_key)
        self.assertEqual({"user-a", "user-b"}, set(self.store.rows.keys()))


if __name__ == "__main__":
    unittest.main()
