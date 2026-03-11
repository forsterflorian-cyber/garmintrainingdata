from __future__ import annotations

import unittest

from backend.services.sync_status_service import SYNC_STATUS_TABLE, SyncStatusService


class FakeResponse:
    def __init__(self, data=None):
        self.data = data or []


class FakeTableQuery:
    def __init__(self, client: "FakeSupabase", table_name: str):
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.payload = None
        self.filters = {}

    def select(self, _columns: str):
        self.operation = "select"
        return self

    def upsert(self, payload, on_conflict=None):
        self.operation = "upsert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def eq(self, field: str, value):
        self.filters[field] = value
        return self

    def limit(self, _value: int):
        return self

    def execute(self):
        return self.client.execute(self)


class FakeSupabase:
    def __init__(self):
        self.rows = {}

    def table(self, table_name: str):
        if table_name != SYNC_STATUS_TABLE:
            raise AssertionError(f"Unexpected table: {table_name}")
        return FakeTableQuery(self, table_name)

    def execute(self, query: FakeTableQuery):
        user_id = query.filters.get("user_id") or (query.payload or {}).get("user_id")
        if query.operation == "select":
            row = self.rows.get(user_id)
            return FakeResponse([dict(row)] if row else [])
        if query.operation == "upsert":
            current = dict(self.rows.get(user_id) or {"user_id": user_id})
            current.update(query.payload or {})
            self.rows[user_id] = current
            return FakeResponse([dict(current)])
        if query.operation == "update":
            current = self.rows.get(user_id)
            if current is None:
                return FakeResponse([])
            current.update(query.payload or {})
            self.rows[user_id] = current
            return FakeResponse([dict(current)])
        raise AssertionError(f"Unexpected operation: {query.operation}")


class SyncStatusServiceHardeningTests(unittest.TestCase):
    def test_update_status_initializes_missing_row_before_update(self):
        client = FakeSupabase()
        service = SyncStatusService(client)

        updated = service.update_status("user-1", {"sync_state": "success", "status_reason": "completed"})

        self.assertEqual(updated["user_id"], "user-1")
        self.assertEqual(updated["sync_state"], "success")
        self.assertEqual(updated["status_reason"], "completed")
        self.assertEqual(client.rows["user-1"]["lock_version"], 0)


if __name__ == "__main__":
    unittest.main()
