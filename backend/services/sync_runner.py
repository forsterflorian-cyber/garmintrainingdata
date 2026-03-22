from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.services.sync_decision import SyncPolicy, build_sync_status_response, decide_sync_action
from backend.services.sync_errors import classify_sync_error
from backend.services.sync_status_service import SyncStatusService, utc_now_iso
from dashboard_service import fetch_training_rows, history_from_rows, upsert_training_payload
from garmin_hybrid_report_v62_supabase_ready import (
    export_client_session,
    get_recent_activities,
    load_client,
    main_logic_for_day,
)
from garmin_session_store import GarminSessionStore
from observability import ErrorCategory, ServiceError, get_logger, log_event, log_exception
from training_config import TRAINING_CONFIG


class SyncRunner:
    def __init__(
        self,
        *,
        supabase_client: Any,
        session_store: GarminSessionStore,
        policy: SyncPolicy = SyncPolicy(),
    ):
        self._supabase = supabase_client
        self._store = session_store
        self._policy = policy
        self._status_service = SyncStatusService(supabase_client)
        self._logger = get_logger(__name__)

    def get_status_payload(self, user_id: str, *, include_debug: bool = False) -> Dict[str, Any]:
        status = self._status_service.ensure_status(user_id)
        dashboard_needs = self.build_dashboard_needs(user_id)
        return build_sync_status_response(
            status,
            dashboard_needs,
            now=datetime.now(timezone.utc),
            policy=self._policy,
            include_debug=include_debug,
        )

    def decide_action(self, user_id: str, *, trigger_source: str, requested_mode: str = "auto") -> Dict[str, Any]:
        status = self._status_service.ensure_status(user_id)
        dashboard_needs = self.build_dashboard_needs(user_id)
        decision = decide_sync_action(
            status,
            datetime.now(timezone.utc),
            dashboard_needs,
            trigger_source=trigger_source,
            requested_mode=requested_mode,
            policy=self._policy,
        )
        return {
            "status": status,
            "dashboardNeeds": dashboard_needs,
            "decision": decision,
        }

    def start_sync(
        self,
        user_id: str,
        *,
        mode: str,
        trigger_source: str,
        reason: str,
        days: Optional[int] = None,
    ) -> Dict[str, Any]:
        lock_token = uuid.uuid4().hex
        sync_state = "backfilling" if mode == "backfill" else "syncing"
        acquired, status = self._status_service.try_acquire_lock(
            user_id,
            lock_token=lock_token,
            mode=mode,
            sync_state=sync_state,
            status_reason=reason,
            lock_ttl_seconds=self._policy.lock_ttl_seconds,
        )
        if not acquired:
            log_event(
                self._logger,
                logging.INFO,
                category=ErrorCategory.DB,
                event="sync.lock_busy",
                message="Sync already in progress.",
                user_id=user_id,
                mode=mode,
            )
            return {"started": False, "status": status}

        run_id = self._status_service.create_run(user_id, mode=mode, trigger_source=trigger_source)
        log_event(
            self._logger,
            logging.INFO,
            category=ErrorCategory.API,
            event="sync.started",
            message="Sync started.",
            user_id=user_id,
            mode=mode,
            trigger_source=trigger_source,
        )

        try:
            if mode == "update":
                imported_records, days_synced, latest_synced_day = self._run_update_sync_blocking(user_id, lock_token=lock_token)
                status_state = "success"
            elif mode == "backfill":
                imported_records, days_synced, latest_synced_day = self._run_backfill_sync_blocking(user_id, lock_token=lock_token, days=days)
                status_state = "partial_success" if self._missing_days_count(user_id) > 0 else "success"
            else:
                imported_records, days_synced, latest_synced_day = self._run_baseline_rebuild_blocking(user_id, lock_token=lock_token)
                status_state = "success"

            missing_days_count = self._missing_days_count(user_id)
            final_status = self._status_service.release_lock(
                user_id,
                lock_token=lock_token,
                fields={
                    "sync_state": status_state,
                    "sync_mode": mode,
                    "status_reason": "completed",
                    "last_successful_sync_at": utc_now_iso(),
                    "last_finished_sync_at": utc_now_iso(),
                    "last_error_category": None,
                    "last_error_code": None,
                    "last_error_message": None,
                    "cooldown_until": None,
                    "consecutive_failure_count": 0,
                    "last_synced_day": latest_synced_day,
                    "missing_days_count": missing_days_count,
                    "stale_score": self._stale_score(missing_days_count),
                    "backfill_recommended": missing_days_count > self._policy.backfill_threshold_days,
                    "baseline_rebuild_recommended": False,
                },
            )
            self._status_service.finish_run(
                run_id,
                status=status_state,
                records_imported=imported_records,
                days_synced=days_synced,
            )
            self._safe_mark_account_sync_state(
                user_id,
                sync_status="ok",
                sync_error=None,
                last_sync_at=utc_now_iso(),
            )
            log_event(
                self._logger,
                logging.INFO,
                category=ErrorCategory.API,
                event="sync.finished",
                message="Sync finished.",
                user_id=user_id,
                mode=mode,
                imported_records=imported_records,
                days_synced=days_synced,
            )
            return {"started": True, "status": final_status}
        except Exception as exc:
            final_status = self._handle_sync_failure(
                user_id=user_id,
                lock_token=lock_token,
                run_id=run_id,
                mode=mode,
                exc=exc,
            )
            return {"started": True, "status": final_status}

    def _run_update_sync_blocking(self, user_id: str, *, lock_token: str) -> tuple[int, int, Optional[str]]:
        rows = fetch_training_rows(
            self._supabase,
            user_id,
            limit=TRAINING_CONFIG.windows.dashboard_history_limit,
        )
        recent_days = [
            (date.today() - timedelta(days=offset)).isoformat()
            for offset in range(self._policy.incremental_sync_days - 1, -1, -1)
        ]
        gap_fill_days = [
            day
            for day in self._missing_day_values(rows, window_days=self._policy.missing_days_window_days)
            if day not in recent_days
        ][: self._policy.incremental_gap_fill_days]
        return self._sync_days(
            user_id,
            lock_token=lock_token,
            target_days=[*recent_days, *gap_fill_days],
        )

    def _run_backfill_sync_blocking(self, user_id: str, *, lock_token: str, days: Optional[int]) -> tuple[int, int, Optional[str]]:
        requested_days = self._policy.initial_backfill_days if days is None else max(1, int(days))
        rows = fetch_training_rows(
            self._supabase,
            user_id,
            limit=TRAINING_CONFIG.windows.dashboard_history_limit,
        )
        target_days = self._missing_day_values(rows, window_days=requested_days)
        if not target_days:
            return 0, 0, None
        return self._sync_days(user_id, lock_token=lock_token, target_days=target_days)

    def _run_baseline_rebuild_blocking(self, user_id: str, *, lock_token: str) -> tuple[int, int, Optional[str]]:
        return self._sync_recent_window(user_id, lock_token=lock_token, days=TRAINING_CONFIG.windows.chronic_load_days)

    def _sync_recent_window(self, user_id: str, *, lock_token: str, days: int) -> tuple[int, int, Optional[str]]:
        target_days = [
            (date.today() - timedelta(days=offset)).isoformat()
            for offset in range(days - 1, -1, -1)
        ]
        return self._sync_days(user_id, lock_token=lock_token, target_days=target_days)

    def _sync_days(self, user_id: str, *, lock_token: str, target_days: List[str]) -> tuple[int, int, Optional[str]]:
        if not target_days:
            return 0, 0, None

        client, _account = self._build_authenticated_client(user_id)
        rows = fetch_training_rows(
            self._supabase,
            user_id,
            limit=TRAINING_CONFIG.windows.dashboard_history_limit,
        )
        history = history_from_rows(rows)
        recent_activities = get_recent_activities(client, TRAINING_CONFIG.windows.default_activity_limit)

        imported_records = 0
        days_synced = 0
        latest_synced_day: Optional[str] = None
        for day in sorted(set(target_days)):
            self._status_service.refresh_lock(user_id, lock_token=lock_token, lock_ttl_seconds=self._policy.lock_ttl_seconds)
            payload = main_logic_for_day(
                day=day,
                mode="hybrid",
                history=history,
                client=client,
                recent_activities=recent_activities,
                persist_history=False,
            )
            upsert_training_payload(self._supabase, user_id, payload)
            history["days"][day] = {
                "morning": payload.get("morning"),
                "summary": payload.get("summary") or {},
            }
            imported_records += 1
            days_synced += 1
            latest_synced_day = day
        return imported_records, days_synced, latest_synced_day

    def _build_authenticated_client(self, user_id: str, retry_count: int = 3):
        """Build authenticated client with retry logic for session conflicts."""
        import time
        
        account = self._store.fetch_account(user_id)
        if not account:
            raise ServiceError("Garmin account missing", status_code=400, category=ErrorCategory.AUTH)

        credentials = account.credentials()
        if not credentials:
            raise ServiceError("Garmin credentials missing", status_code=400, category=ErrorCategory.AUTH)

        email, password = credentials
        session_payload = account.session_payload()
        client = load_client(email=email, password=password, session_data=session_payload)

        refreshed_session = export_client_session(client)
        if not refreshed_session:
            return client, account

        # Retry-Logik für Session-Speicherung
        for attempt in range(retry_count):
            try:
                # Immer die aktuelle Version laden
                current_account = self._store.fetch_account(user_id)
                expected_version = current_account.garmin_session_version if current_account else None
                
                self._store.save_session_atomically(
                    user_id,
                    refreshed_session,
                    expected_version=expected_version,
                )
                break  # Erfolg
            except ServiceError as exc:
                if exc.status_code == 409:  # Conflict
                    if attempt < retry_count - 1:
                        # Kurz warten und erneut versuchen
                        time.sleep(0.1 * (attempt + 1))
                        log_event(
                            self._logger,
                            logging.WARNING,
                            category=ErrorCategory.DB,
                            event="sync.session_refresh_retry",
                            message=f"Session refresh conflict, retry {attempt + 1}/{retry_count}",
                            user_id=user_id,
                        )
                        continue
                    else:
                        # Letzter Versuch fehlgeschlagen
                        log_event(
                            self._logger,
                            logging.ERROR,
                            category=ErrorCategory.DB,
                            event="sync.session_refresh_failed",
                            message="Session refresh failed after all retries",
                            user_id=user_id,
                        )
                        # Trotzdem Client zurückgeben (Session ist funktional)
                else:
                    raise  # Anderen Fehler weiterwerfen

        return client, account

    def _handle_sync_failure(
        self,
        *,
        user_id: str,
        lock_token: str,
        run_id: Optional[int],
        mode: str,
        exc: Exception,
    ) -> Dict[str, Any]:
        current_status = self._status_service.ensure_status(user_id)
        consecutive_failure_count = int(current_status.get("consecutive_failure_count") or 0) + 1
        classification = classify_sync_error(exc, consecutive_failure_count=consecutive_failure_count)
        sync_state = "blocked" if classification["blocked"] else "error"
        cooldown_until = None
        if classification["retryable"] and classification["cooldownSeconds"]:
            cooldown_until = (datetime.now(timezone.utc) + timedelta(seconds=int(classification["cooldownSeconds"]))).isoformat()

        if classification["category"] == "auth":
            try:
                self._store.clear_session(user_id)
            except ServiceError as clear_exc:
                log_exception(
                    self._logger,
                    category=ErrorCategory.DB,
                    event="sync.session_clear_failed",
                    message="Failed to clear Garmin session after auth error.",
                    exc=clear_exc,
                    user_id=user_id,
                    level=logging.WARNING,
                )

        final_status = self._status_service.release_lock(
            user_id,
            lock_token=lock_token,
            fields={
                "sync_state": sync_state,
                "sync_mode": mode,
                "status_reason": classification["code"],
                "last_finished_sync_at": utc_now_iso(),
                "last_error_category": classification["category"],
                "last_error_code": classification["code"],
                "last_error_message": classification["userMessage"],
                "cooldown_until": cooldown_until,
                "consecutive_failure_count": consecutive_failure_count,
            },
        )
        self._status_service.finish_run(
            run_id,
            status=sync_state,
            error_code=classification["code"],
            error_message=classification["userMessage"],
        )
        log_exception(
            self._logger,
            category=ErrorCategory.API,
            event="sync.failed",
            message="Sync failed.",
            exc=exc,
            user_id=user_id,
            mode=mode,
            error_code=classification["code"],
        )
        self._safe_mark_account_sync_state(
            user_id,
            sync_status=sync_state,
            sync_error=classification["userMessage"],
        )
        return final_status

    def refresh_status_metadata(self, user_id: str) -> Dict[str, Any]:
        missing_days_count = self._missing_days_count(user_id)
        rows = fetch_training_rows(
            self._supabase,
            user_id,
            limit=TRAINING_CONFIG.windows.dashboard_history_limit,
        )
        last_synced_day = self._latest_valid_row_day(rows)
        return self._status_service.update_status(
            user_id,
            {
                "missing_days_count": missing_days_count,
                "last_synced_day": last_synced_day,
                "stale_score": self._stale_score(missing_days_count),
                "backfill_recommended": missing_days_count > self._policy.backfill_threshold_days,
            },
        )

    def build_dashboard_needs(self, user_id: str) -> Dict[str, Any]:
        rows = fetch_training_rows(
            self._supabase,
            user_id,
            limit=TRAINING_CONFIG.windows.dashboard_history_limit,
        )
        account = self._store.fetch_account(user_id)
        latest_data_day = self._latest_valid_row_day(rows)
        missing_days_count = self._missing_days_count_from_rows(rows, window_days=self._policy.missing_days_window_days)
        missing_recent_day = True
        if latest_data_day:
            latest = self._parse_iso_day(latest_data_day)
            if latest is not None:
                missing_recent_day = (date.today() - latest).days > 1
        return {
            "latestDataDay": latest_data_day,
            "missingDaysCount": missing_days_count,
            "missingDaysWindowDays": self._policy.missing_days_window_days,
            "targetHistoryDays": self._policy.initial_backfill_days,
            "historyCoverageDays": self._history_coverage_days(missing_days_count),
            "missingRecentDay": missing_recent_day,
            "hasCredentials": bool(account and account.garmin_email_enc and account.garmin_password_enc),
        }

    def _missing_days_count(self, user_id: str) -> int:
        rows = fetch_training_rows(
            self._supabase,
            user_id,
            limit=TRAINING_CONFIG.windows.dashboard_history_limit,
        )
        return self._missing_days_count_from_rows(rows, window_days=self._policy.missing_days_window_days)

    @staticmethod
    def _missing_days_count_from_rows(rows: List[Dict[str, Any]], window_days: int = 180) -> int:
        day_set = SyncRunner._valid_row_days(rows)
        today_value = date.today()
        missing = 0
        for offset in range(window_days):
            day = (today_value - timedelta(days=offset)).isoformat()
            if day not in day_set:
                missing += 1
        return missing

    @staticmethod
    def _missing_day_values(rows: List[Dict[str, Any]], *, window_days: int) -> List[str]:
        day_set = SyncRunner._valid_row_days(rows)
        today_value = date.today()
        missing_days: List[str] = []
        for offset in range(window_days - 1, -1, -1):
            day = (today_value - timedelta(days=offset)).isoformat()
            if day not in day_set:
                missing_days.append(day)
        return missing_days

    @staticmethod
    def _stale_score(missing_days_count: int) -> int:
        return min(100, missing_days_count * 5)

    def _history_coverage_days(self, missing_days_count: int) -> int:
        return max(0, self._policy.initial_backfill_days - int(missing_days_count or 0))

    @staticmethod
    def _latest_valid_row_day(rows: List[Dict[str, Any]]) -> Optional[str]:
        for row in reversed(rows):
            if not isinstance(row, dict):
                continue
            day = SyncRunner._normalized_iso_day(row.get("date"))
            if day is not None:
                return day
        return None

    @staticmethod
    def _valid_row_days(rows: List[Dict[str, Any]]) -> set[str]:
        days: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            day = SyncRunner._normalized_iso_day(row.get("date"))
            if day is not None:
                days.add(day)
        return days

    @staticmethod
    def _normalized_iso_day(value: Any) -> Optional[str]:
        parsed = SyncRunner._parse_iso_day(value)
        return parsed.isoformat() if parsed is not None else None

    @staticmethod
    def _parse_iso_day(value: Any):
        if not isinstance(value, str):
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None

    def _safe_mark_account_sync_state(
        self,
        user_id: str,
        *,
        sync_status: Optional[str] = None,
        sync_error: Optional[str] = None,
        last_sync_at: Optional[str] = None,
    ) -> None:
        try:
            self._store.mark_sync_state(
                user_id,
                sync_status=sync_status,
                sync_error=sync_error,
                last_sync_at=last_sync_at,
            )
        except ServiceError as exc:
            log_exception(
                self._logger,
                category=ErrorCategory.DB,
                event="sync.account_state_update_failed",
                message="Failed to update Garmin account sync state.",
                exc=exc,
                user_id=user_id,
                level=logging.WARNING,
            )
