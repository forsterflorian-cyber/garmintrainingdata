import sys
import types
import unittest
from unittest.mock import patch

fake_crypto_utils = types.ModuleType("crypto_utils")
fake_crypto_utils.encrypt = lambda value: f"enc:{value}"
fake_crypto_utils.decrypt = lambda value: value.removeprefix("enc:")
sys.modules.setdefault("crypto_utils", fake_crypto_utils)

from garmin_session_store import GarminSessionStore, TABLE_NAME
from observability import ServiceError


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or []


class MissingSessionColumnError(Exception):
    def __init__(self, column: str = "garmin_session_enc"):
        self.code = "42703"
        self.message = f"column {TABLE_NAME}.{column} does not exist"
        self.details = None
        super().__init__({"message": self.message, "code": self.code, "hint": None, "details": None})


class UniqueOwnershipConstraintError(Exception):
    def __init__(self, column: str):
        self.code = "23505"
        self.message = f"duplicate key value violates unique constraint user_garmin_accounts_{column}_unique"
        self.details = f"Key ({column}) already exists."
        super().__init__({"message": self.message, "code": self.code, "details": self.details})


class FakeTableQuery:
    def __init__(self, client: "FakeSupabase", table_name: str):
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.select_columns = None
        self.filters = {}
        self.limit_value = None
        self.payload = None
        self.on_conflict = None

    def select(self, columns: str):
        self.operation = "select"
        self.select_columns = columns
        return self

    def eq(self, field: str, value):
        self.filters[field] = value
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def upsert(self, payload, on_conflict=None):
        self.operation = "upsert"
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def execute(self):
        return self.client.execute(self)


class FakeSupabase:
    def __init__(self, *, rows=None, missing_session_columns: bool = False):
        self.rows = {user_id: dict(row) for user_id, row in (rows or {}).items()}
        self.missing_session_columns = missing_session_columns
        self.operations = []

    def table(self, table_name: str):
        if table_name != TABLE_NAME:
            raise AssertionError(f"Unexpected table: {table_name}")
        return FakeTableQuery(self, table_name)

    def execute(self, query: FakeTableQuery):
        self.operations.append(
            {
                "operation": query.operation,
                "select_columns": query.select_columns,
                "filters": dict(query.filters),
                "payload": dict(query.payload) if isinstance(query.payload, dict) else query.payload,
            }
        )

        if query.operation == "select":
            if self.missing_session_columns and "garmin_session_enc" in (query.select_columns or ""):
                raise MissingSessionColumnError()

            matches = [
                dict(row)
                for row in self.rows.values()
                if all(row.get(field) == value for field, value in query.filters.items())
            ]
            if query.limit_value is not None:
                matches = matches[: query.limit_value]
            return FakeResponse([self._project_row(row, query.select_columns) for row in matches])

        if query.operation == "upsert":
            if self.missing_session_columns and any(key.startswith("garmin_session_") for key in query.payload):
                raise MissingSessionColumnError()

            user_id = query.payload["user_id"]
            self._ensure_unique_ownership_keys(user_id, query.payload)
            current = self.rows.get(user_id, {"user_id": user_id})
            current.update(query.payload)
            self.rows[user_id] = current
            return FakeResponse([dict(current)])

        if query.operation == "update":
            if self.missing_session_columns and (
                any(key.startswith("garmin_session_") for key in query.payload)
                or "garmin_session_version" in query.filters
                or "garmin_session_enc" in (query.select_columns or "")
            ):
                raise MissingSessionColumnError()

            user_id = query.filters.get("user_id")
            current = self.rows.get(user_id)
            if current is None:
                return FakeResponse([])
            if "garmin_session_version" in query.filters:
                current_version = current.get("garmin_session_version", 0)
                if current_version != query.filters["garmin_session_version"]:
                    return FakeResponse([])
            self._ensure_unique_ownership_keys(user_id, query.payload)
            current.update(query.payload)
            self.rows[user_id] = current
            data = [self._project_row(current, query.select_columns)] if query.select_columns else []
            return FakeResponse(data)

        raise AssertionError(f"Unexpected operation: {query.operation}")

    @staticmethod
    def _project_row(row, columns: str):
        if not columns:
            return dict(row)
        return {column: row.get(column) for column in columns.split(",")}

    def _ensure_unique_ownership_keys(self, user_id: str, payload: dict):
        for column in ("garmin_account_key", "garmin_login_key"):
            value = payload.get(column)
            if not value:
                continue
            for existing_user_id, row in self.rows.items():
                if existing_user_id == user_id:
                    continue
                if row.get(column) == value:
                    raise UniqueOwnershipConstraintError(column)


class GarminSessionStoreCompatibilityTests(unittest.TestCase):
    def test_fetch_account_falls_back_to_legacy_select_when_session_columns_are_missing(self):
        client = FakeSupabase(
            rows={
                "user-1": {
                    "user_id": "user-1",
                    "garmin_email_enc": "enc:mail",
                    "garmin_password_enc": "enc:pass",
                    "sync_status": "connected",
                }
            },
            missing_session_columns=True,
        )
        store = GarminSessionStore(client)

        account = store.fetch_account("user-1")

        self.assertEqual(account.user_id, "user-1")
        self.assertIsNone(account.garmin_session_enc)
        self.assertEqual(account.garmin_session_version, 0)
        self.assertFalse(store._session_columns_available)
        self.assertIn("garmin_session_enc", client.operations[0]["select_columns"])
        self.assertEqual(client.operations[1]["select_columns"], store._legacy_select_columns)

    def test_save_connected_account_skips_session_fields_on_legacy_schema(self):
        client = FakeSupabase(missing_session_columns=True)
        store = GarminSessionStore(client)

        with patch("garmin_session_store.encrypt", side_effect=lambda value: f"enc:{value}"):
            account = store.save_connected_account("user-1", "mail@example.com", "secret", "session-json")

        upsert_ops = [operation for operation in client.operations if operation["operation"] == "upsert"]
        self.assertEqual(len(upsert_ops), 1)
        self.assertEqual(
            upsert_ops[0]["payload"],
            {
                "user_id": "user-1",
                "garmin_email_enc": "enc:mail@example.com",
                "garmin_password_enc": "enc:secret",
                "sync_status": "connected",
                "sync_error": None,
            },
        )
        self.assertEqual(account.garmin_email_enc, "enc:mail@example.com")
        self.assertEqual(account.garmin_password_enc, "enc:secret")
        self.assertIsNone(account.garmin_session_enc)
        self.assertEqual(account.garmin_session_version, 0)

    def test_save_session_atomically_becomes_noop_on_legacy_schema(self):
        client = FakeSupabase(
            rows={
                "user-1": {
                    "user_id": "user-1",
                    "garmin_email_enc": "enc:mail",
                    "garmin_password_enc": "enc:pass",
                    "sync_status": "connected",
                }
            },
            missing_session_columns=True,
        )
        store = GarminSessionStore(client)

        with patch("garmin_session_store.encrypt", side_effect=lambda value: f"enc:{value}"):
            account = store.save_session_atomically("user-1", "session-json", expected_version=0)

        write_ops = [
            operation
            for operation in client.operations
            if operation["operation"] in {"upsert", "update"}
        ]
        self.assertEqual(write_ops, [])
        self.assertEqual(account.user_id, "user-1")
        self.assertIsNone(account.garmin_session_enc)
        self.assertEqual(account.garmin_session_version, 0)

    def test_find_conflicting_account_detects_legacy_row_by_stored_login_identifier(self):
        client = FakeSupabase(
            rows={
                "user-a": {
                    "user_id": "user-a",
                    "garmin_email_enc": "enc:garmin-x@example.com",
                    "garmin_password_enc": "enc:secret",
                    "sync_status": "connected",
                }
            }
        )
        store = GarminSessionStore(client)

        conflict = store.find_conflicting_account(
            user_id="user-b",
            garmin_account_key="garmin_guid:guid-x",
            garmin_login_key="garmin-x@example.com",
        )

        self.assertIsNotNone(conflict)
        self.assertEqual("user-a", conflict.user_id)

    def test_save_connected_account_maps_unique_ownership_violation_to_clear_409(self):
        client = FakeSupabase(
            rows={
                "user-a": {
                    "user_id": "user-a",
                    "garmin_email_enc": "enc:garmin-x@example.com",
                    "garmin_password_enc": "enc:secret",
                    "garmin_account_key": "garmin_guid:guid-x",
                    "garmin_login_key": "garmin-x@example.com",
                    "garmin_session_version": 1,
                }
            }
        )
        store = GarminSessionStore(client)

        with patch("garmin_session_store.encrypt", side_effect=lambda value: f"enc:{value}"):
            with self.assertRaises(ServiceError) as context:
                store.save_connected_account(
                    "user-b",
                    "garmin-x@example.com",
                    "other-secret",
                    "session-json",
                    garmin_account_key="garmin_guid:guid-x",
                    garmin_account_key_source="garmin_guid",
                    garmin_login_key="garmin-x@example.com",
                )

        self.assertEqual(409, context.exception.status_code)
        self.assertEqual(
            "This Garmin account is already connected to another account.",
            context.exception.public_message,
        )


if __name__ == "__main__":
    unittest.main()
