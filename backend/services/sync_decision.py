from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.services.sync_status_service import is_lock_active, parse_iso


TERMINAL_SYNC_STATES = {"fresh", "success", "partial_success", "error", "blocked", "never_synced", "stale"}


@dataclass(frozen=True)
class SyncPolicy:
    freshness_threshold_hours: int = int(os.environ.get("SYNC_FRESHNESS_HOURS", "6"))
    stale_threshold_hours: int = int(os.environ.get("SYNC_STALE_HOURS", "12"))
    backfill_threshold_days: int = int(os.environ.get("SYNC_BACKFILL_THRESHOLD_DAYS", "3"))
    auto_backfill_limit_days: int = int(os.environ.get("SYNC_AUTO_BACKFILL_LIMIT_DAYS", "3"))
    lock_ttl_seconds: int = int(os.environ.get("SYNC_LOCK_TTL_SECONDS", "600"))
    auto_poll_seconds: int = int(os.environ.get("SYNC_POLL_SECONDS", "5"))


def decide_sync_action(
    sync_status: Dict[str, Any],
    now: datetime,
    dashboard_needs: Dict[str, Any],
    *,
    trigger_source: str,
    requested_mode: str = "auto",
    policy: SyncPolicy = SyncPolicy(),
) -> Dict[str, Any]:
    state_before = normalize_sync_state(sync_status, now, dashboard_needs, policy=policy)
    missing_days_count = int(dashboard_needs.get("missingDaysCount") or 0)
    has_credentials = credentials_available(dashboard_needs)
    backfill_recommended = missing_days_count > policy.backfill_threshold_days
    small_auto_backfill = 1 < missing_days_count <= policy.auto_backfill_limit_days
    baseline_rebuild_recommended = bool(sync_status.get("baseline_rebuild_recommended"))
    cooldown_active = is_cooldown_active(sync_status, now)

    if requested_mode != "auto":
        if state_before in {"syncing", "backfilling"}:
            return result(False, requested_mode, "already_running", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)
        if not has_credentials:
            return result(False, requested_mode, "credentials_missing", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)
        if is_persistent_block(sync_status):
            return result(False, requested_mode, blocked_reason(sync_status), state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)
        if cooldown_active:
            return result(False, requested_mode, "cooldown_active", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)
        return result(True, requested_mode, "manual_request", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)

    if not sync_status.get("auto_sync_enabled", True):
        return result(False, "update", "auto_sync_disabled", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)

    if state_before in {"syncing", "backfilling"}:
        return result(False, "update", "already_running", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)

    if not has_credentials:
        return result(False, "update", "credentials_missing", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)

    if is_persistent_block(sync_status):
        return result(False, "update", blocked_reason(sync_status), state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)
    if cooldown_active:
        return result(False, "update", "cooldown_active", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)
    if state_before == "error":
        return result(False, "update", "sync_error", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)
    if state_before == "partial_success":
        return result(False, "update", "partial_success", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)

    if state_before == "never_synced":
        return result(True, "update", "never_synced", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)

    if dashboard_needs.get("missingRecentDay") or state_before == "stale":
        if small_auto_backfill:
            return result(True, "backfill", "gap_detected", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)
        return result(
            True,
            "update",
            "missing_recent_day" if dashboard_needs.get("missingRecentDay") else "stale_data",
            state_before,
            cooldown_active,
            backfill_recommended,
            baseline_rebuild_recommended,
        )

    return result(False, "update", "fresh_no_action", state_before, cooldown_active, backfill_recommended, baseline_rebuild_recommended)


def build_sync_status_response(
    sync_status: Dict[str, Any],
    dashboard_needs: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    policy: SyncPolicy = SyncPolicy(),
    include_debug: bool = False,
) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    decision = decide_sync_action(sync_status, now, dashboard_needs, trigger_source="status", requested_mode="auto", policy=policy)
    normalized_state = normalize_sync_state(sync_status, now, dashboard_needs, policy=policy)
    manual_allowed = (
        credentials_available(dashboard_needs)
        and normalized_state not in {"syncing", "backfilling"}
        and not is_persistent_block(sync_status)
        and not is_cooldown_active(sync_status, now)
    )

    payload = {
        "syncState": normalized_state,
        "syncMode": sync_status.get("sync_mode"),
        "lastSuccessfulSyncAt": sync_status.get("last_successful_sync_at"),
        "lastAttemptedSyncAt": sync_status.get("last_attempted_sync_at"),
        "lastStartedSyncAt": sync_status.get("last_started_sync_at"),
        "lastFinishedSyncAt": sync_status.get("last_finished_sync_at"),
        "cooldownUntil": sync_status.get("cooldown_until"),
        "autoSyncEnabled": bool(sync_status.get("auto_sync_enabled", True)),
        "autoSyncRecommended": bool(decision["should_start"]),
        "autoSyncMode": decision["mode"] if decision["should_start"] else None,
        "backfillRecommended": decision["backfill_recommended"],
        "baselineRebuildRecommended": decision["baseline_rebuild_recommended"],
        "missingDaysCount": int(dashboard_needs.get("missingDaysCount") or 0),
        "canStartSync": manual_allowed,
        "statusReason": decision["reason"],
        "isLocked": is_lock_active(sync_status),
        "lastErrorCode": sync_status.get("last_error_code"),
        "lastErrorMessage": sync_status.get("last_error_message"),
        "staleScore": int(sync_status.get("stale_score") or 0),
        "terminal": normalized_state in TERMINAL_SYNC_STATES,
    }
    if include_debug:
        payload["debug"] = {
            "syncState": normalized_state,
            "lockActive": is_lock_active(sync_status),
            "cooldownActive": is_cooldown_active(sync_status, now),
            "cooldownUntil": sync_status.get("cooldown_until"),
            "missingDaysCount": int(dashboard_needs.get("missingDaysCount") or 0),
            "autoSyncDecisionReason": decision["reason"],
            "lastErrorCode": sync_status.get("last_error_code"),
        }
    return payload


def normalize_sync_state(
    sync_status: Dict[str, Any],
    now: datetime,
    dashboard_needs: Dict[str, Any],
    *,
    policy: SyncPolicy,
) -> str:
    raw_state = sync_status.get("sync_state") or "never_synced"
    last_successful_sync_at = parse_iso(sync_status.get("last_successful_sync_at"))
    last_finished_sync_at = parse_iso(sync_status.get("last_finished_sync_at"))

    if raw_state in {"syncing", "backfilling"} and is_lock_active(sync_status):
        return raw_state

    if not credentials_available(dashboard_needs):
        return "blocked"

    if is_persistent_block(sync_status):
        return "blocked"

    if raw_state == "error":
        return "error"
    if raw_state == "partial_success" and last_finished_sync_at and last_successful_sync_at and last_finished_sync_at >= last_successful_sync_at:
        return "partial_success"

    if last_successful_sync_at is None:
        return "never_synced"

    age_hours = (now - last_successful_sync_at).total_seconds() / 3600.0
    if age_hours <= policy.freshness_threshold_hours:
        return "fresh"
    return "stale"


def is_cooldown_active(sync_status: Dict[str, Any], now: datetime) -> bool:
    cooldown_until = parse_iso(sync_status.get("cooldown_until"))
    return bool(cooldown_until and cooldown_until > now)


def is_persistent_block(sync_status: Dict[str, Any]) -> bool:
    if sync_status.get("sync_state") == "blocked":
        return True
    if sync_status.get("last_error_category") in {"auth", "validation", "config"}:
        return True
    return False


def blocked_reason(sync_status: Dict[str, Any]) -> str:
    if sync_status.get("last_error_category") in {"auth", "validation", "config"}:
        return "credentials_invalid"
    return "blocked"


def credentials_available(dashboard_needs: Dict[str, Any]) -> bool:
    return bool(dashboard_needs.get("hasCredentials", True))


def result(
    should_start: bool,
    mode: str,
    reason: str,
    state_before: str,
    cooldown_active: bool,
    backfill_recommended: bool,
    baseline_rebuild_recommended: bool,
) -> Dict[str, Any]:
    return {
        "should_start": should_start,
        "mode": mode,
        "reason": reason,
        "state_before": state_before,
        "cooldown_active": cooldown_active,
        "backfill_recommended": backfill_recommended,
        "baseline_rebuild_recommended": baseline_rebuild_recommended,
    }
