from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


SYNC_STATUS_TABLE = "sync_status"
SYNC_RUNS_TABLE = "sync_runs"


class SyncStatusService:
    def __init__(self, supabase_client: Any):
        self._supabase = supabase_client

    def ensure_status(self, user_id: str) -> Dict[str, Any]:
        status = self.fetch_status(user_id, ensure=False)
        if status is not None:
            return status

        now_iso = utc_now_iso()
        (
            self._supabase.table(SYNC_STATUS_TABLE)
            .upsert(
                {
                    "user_id": user_id,
                    "sync_state": "never_synced",
                    "updated_at": now_iso,
                    "lock_version": 0,
                },
                on_conflict="user_id",
            )
            .execute()
        )
        return self.fetch_status(user_id, ensure=False) or {
            "user_id": user_id,
            "sync_state": "never_synced",
            "lock_version": 0,
        }

    def fetch_status(self, user_id: str, *, ensure: bool = True) -> Optional[Dict[str, Any]]:
        if ensure:
            self.ensure_status(user_id)

        response = (
            self._supabase.table(SYNC_STATUS_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return response.data[0]

    def update_status(self, user_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        payload = {**fields, "updated_at": utc_now_iso()}
        response = (
            self._supabase.table(SYNC_STATUS_TABLE)
            .update(payload)
            .eq("user_id", user_id)
            .execute()
        )
        return response.data[0] if response.data else self.ensure_status(user_id)

    def try_acquire_lock(
        self,
        user_id: str,
        *,
        lock_token: str,
        mode: str,
        sync_state: str,
        status_reason: str,
        lock_ttl_seconds: int,
    ) -> tuple[bool, Dict[str, Any]]:
        status = self.ensure_status(user_id)
        if is_lock_active(status):
            return False, status

        now_iso = utc_now_iso()
        expires_iso = utc_in_seconds_iso(lock_ttl_seconds)
        version = int(status.get("lock_version") or 0)
        
        response = (
            self._supabase.table(SYNC_STATUS_TABLE)
            .update(
                {
                    "lock_token": lock_token,
                    "lock_acquired_at": now_iso,
                    "lock_expires_at": expires_iso,
                    "lock_version": version + 1,
                    "sync_state": sync_state,
                    "sync_mode": mode,
                    "status_reason": status_reason,
                    "last_attempted_sync_at": now_iso,
                    "last_started_sync_at": now_iso,
                    "updated_at": now_iso,
                }
            )
            .eq("user_id", user_id)
            .eq("lock_version", version)
            .execute()
        )
        if response.data:
            return True, response.data[0]
        return False, self.ensure_status(user_id)

    def refresh_lock(self, user_id: str, *, lock_token: str, lock_ttl_seconds: int) -> Optional[Dict[str, Any]]:
        response = (
            self._supabase.table(SYNC_STATUS_TABLE)
            .update(
                {
                    "lock_expires_at": utc_in_seconds_iso(lock_ttl_seconds),
                    "updated_at": utc_now_iso(),
                }
            )
            .eq("user_id", user_id)
            .eq("lock_token", lock_token)
            .execute()
        )
        return response.data[0] if response.data else None

    def release_lock(self, user_id: str, *, lock_token: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        current = self.ensure_status(user_id)
        version = int(current.get("lock_version") or 0)
        payload = {
            **fields,
            "lock_token": None,
            "lock_acquired_at": None,
            "lock_expires_at": None,
            "lock_version": version + 1,
            "updated_at": utc_now_iso(),
        }
        response = (
            self._supabase.table(SYNC_STATUS_TABLE)
            .update(payload)
            .eq("user_id", user_id)
            .eq("lock_token", lock_token)
            .execute()
        )
        return response.data[0] if response.data else self.ensure_status(user_id)

    def create_run(self, user_id: str, *, mode: str, trigger_source: str) -> Optional[int]:
        response = (
            self._supabase.table(SYNC_RUNS_TABLE)
            .insert(
                {
                    "user_id": user_id,
                    "mode": mode,
                    "trigger_source": trigger_source,
                    "status": "started",
                    "started_at": utc_now_iso(),
                }
            )
            .execute()
        )
        if not response.data:
            return None
        return int(response.data[0]["id"])

    def finish_run(
        self,
        run_id: Optional[int],
        *,
        status: str,
        records_imported: int = 0,
        days_synced: int = 0,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        if run_id is None:
            return
        (
            self._supabase.table(SYNC_RUNS_TABLE)
            .update(
                {
                    "status": status,
                    "finished_at": utc_now_iso(),
                    "records_imported": records_imported,
                    "days_synced": days_synced,
                    "error_code": error_code,
                    "error_message": error_message,
                }
            )
            .eq("id", run_id)
            .execute()
        )


def is_lock_active(status: Optional[Dict[str, Any]]) -> bool:
    if not status:
        return False
    token = status.get("lock_token")
    expires_at_raw = status.get("lock_expires_at")
    if not token or not expires_at_raw:
        return False
    expires_at = parse_iso(expires_at_raw)
    if not expires_at:
        return False
    return expires_at > datetime.now(timezone.utc)


def parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_in_seconds_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()