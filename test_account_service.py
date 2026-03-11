from __future__ import annotations

import unittest

from backend.services.account_service import (
    ACCOUNT_DELETE_REDIRECT,
    AccountService,
    DELETE_CONFIRMATION_TEXT,
    GARMIN_ACCOUNTS_TABLE,
)
from backend.services.sync_status_service import SYNC_RUNS_TABLE, SYNC_STATUS_TABLE
from observability import ServiceError


TRAINING_DAYS_TABLE = "training_days"


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or []


class FakeTableQuery:
    def __init__(self, client: "FakeSupabase", table_name: str):
        self.client = client
        self.table_name = table_name
        self.filters = {}
        self.operation = None

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, field: str, value):
        self.filters[field] = value
        return self

    def execute(self):
        return self.client.execute(self)


class FakeSupabase:
    def __init__(self, tables=None):
        self.tables = {name: [dict(row) for row in rows] for name, rows in (tables or {}).items()}

    def table(self, table_name: str):
        self.tables.setdefault(table_name, [])
        return FakeTableQuery(self, table_name)

    def execute(self, query: FakeTableQuery):
        if query.operation != "delete":
            raise AssertionError(f"Unexpected operation: {query.operation}")

        existing = self.tables.setdefault(query.table_name, [])
        removed = []
        kept = []
        for row in existing:
            if all(row.get(field) == value for field, value in query.filters.items()):
                removed.append(dict(row))
            else:
                kept.append(dict(row))
        self.tables[query.table_name] = kept
        return FakeResponse(removed)


class AccountServiceTests(unittest.TestCase):
    def test_delete_account_rejects_invalid_confirmation(self):
        client = FakeSupabase()
        deleted_users = []
        service = AccountService(client, auth_user_deleter=lambda user_id: deleted_users.append(user_id) or True)

        with self.assertRaises(ServiceError) as context:
            service.delete_account("user-1", confirmation_text="delete")

        self.assertEqual(400, context.exception.status_code)
        self.assertEqual("Type DELETE to confirm account deletion.", context.exception.public_message)
        self.assertEqual([], deleted_users)

    def test_delete_account_removes_user_scoped_rows_and_returns_sign_out_payload(self):
        deleted_users = []
        client = FakeSupabase(
            {
                GARMIN_ACCOUNTS_TABLE: [
                    {"user_id": "user-1", "garmin_email_enc": "a"},
                    {"user_id": "user-2", "garmin_email_enc": "b"},
                ],
                SYNC_STATUS_TABLE: [
                    {"user_id": "user-1", "sync_state": "success"},
                    {"user_id": "user-2", "sync_state": "success"},
                ],
                SYNC_RUNS_TABLE: [
                    {"id": 1, "user_id": "user-1"},
                    {"id": 2, "user_id": "user-2"},
                ],
                TRAINING_DAYS_TABLE: [
                    {"user_id": "user-1", "date": "2026-03-10"},
                    {"user_id": "user-2", "date": "2026-03-10"},
                ],
            }
        )
        service = AccountService(client, auth_user_deleter=lambda user_id: deleted_users.append(user_id) or True)

        response = service.delete_account("user-1", confirmation_text=DELETE_CONFIRMATION_TEXT)

        self.assertEqual("deleted", response["status"])
        self.assertTrue(response["signOut"])
        self.assertTrue(response["authUserDeleted"])
        self.assertEqual(ACCOUNT_DELETE_REDIRECT, response["redirectTo"])
        self.assertEqual(["user-1"], deleted_users)
        self.assertEqual([{"user_id": "user-2", "garmin_email_enc": "b"}], client.tables[GARMIN_ACCOUNTS_TABLE])
        self.assertEqual([{"user_id": "user-2", "sync_state": "success"}], client.tables[SYNC_STATUS_TABLE])
        self.assertEqual([{"id": 2, "user_id": "user-2"}], client.tables[SYNC_RUNS_TABLE])
        self.assertEqual([{"user_id": "user-2", "date": "2026-03-10"}], client.tables[TRAINING_DAYS_TABLE])

    def test_delete_account_tolerates_missing_user_rows(self):
        deleted_users = []
        client = FakeSupabase(
            {
                GARMIN_ACCOUNTS_TABLE: [{"user_id": "user-2", "garmin_email_enc": "b"}],
                SYNC_STATUS_TABLE: [],
                SYNC_RUNS_TABLE: [{"id": 2, "user_id": "user-2"}],
                TRAINING_DAYS_TABLE: [],
            }
        )
        service = AccountService(client, auth_user_deleter=lambda user_id: deleted_users.append(user_id) or True)

        response = service.delete_account("user-1", confirmation_text=DELETE_CONFIRMATION_TEXT)

        self.assertEqual("deleted", response["status"])
        self.assertEqual(["user-1"], deleted_users)
        self.assertEqual([{"user_id": "user-2", "garmin_email_enc": "b"}], client.tables[GARMIN_ACCOUNTS_TABLE])
        self.assertEqual([{"id": 2, "user_id": "user-2"}], client.tables[SYNC_RUNS_TABLE])

    def test_delete_account_raises_clear_error_when_auth_delete_fails(self):
        client = FakeSupabase(
            {
                GARMIN_ACCOUNTS_TABLE: [{"user_id": "user-1"}],
                SYNC_STATUS_TABLE: [{"user_id": "user-1"}],
                SYNC_RUNS_TABLE: [{"id": 1, "user_id": "user-1"}],
                TRAINING_DAYS_TABLE: [{"user_id": "user-1", "date": "2026-03-10"}],
            }
        )

        def failing_auth_delete(_user_id: str) -> bool:
            raise RuntimeError("admin delete failed")

        service = AccountService(client, auth_user_deleter=failing_auth_delete)

        with self.assertRaises(ServiceError) as context:
            service.delete_account("user-1", confirmation_text=DELETE_CONFIRMATION_TEXT)

        self.assertEqual(500, context.exception.status_code)
        self.assertEqual("Account deletion could not be completed. Please try again.", context.exception.public_message)


if __name__ == "__main__":
    unittest.main()
