from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.services.garmin_account_identity import normalize_garmin_login
from crypto_utils import decrypt, encrypt
from observability import ErrorCategory, ServiceError, get_logger, log_event, log_exception


TABLE_NAME = "user_garmin_accounts"
SESSION_COLUMNS = (
    "garmin_session_enc",
    "garmin_session_version",
    "garmin_session_updated_at",
)
OWNERSHIP_COLUMNS = (
    "garmin_account_key",
    "garmin_account_key_source",
    "garmin_login_key",
)


@dataclass
class GarminAccount:
    user_id: str
    garmin_email_enc: Optional[str] = None
    garmin_password_enc: Optional[str] = None
    garmin_session_enc: Optional[str] = None
    garmin_session_version: int = 0
    garmin_account_key: Optional[str] = None
    garmin_account_key_source: Optional[str] = None
    garmin_login_key: Optional[str] = None
    sync_status: Optional[str] = None
    sync_error: Optional[str] = None
    last_sync_at: Optional[str] = None
    garmin_session_updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "GarminAccount":
        return cls(
            user_id=row["user_id"],
            garmin_email_enc=row.get("garmin_email_enc"),
            garmin_password_enc=row.get("garmin_password_enc"),
            garmin_session_enc=row.get("garmin_session_enc"),
            garmin_session_version=int(row.get("garmin_session_version") or 0),
            garmin_account_key=row.get("garmin_account_key"),
            garmin_account_key_source=row.get("garmin_account_key_source"),
            garmin_login_key=row.get("garmin_login_key"),
            sync_status=row.get("sync_status"),
            sync_error=row.get("sync_error"),
            last_sync_at=row.get("last_sync_at"),
            garmin_session_updated_at=row.get("garmin_session_updated_at"),
        )

    def credentials(self) -> Optional[tuple[str, str]]:
        if not self.garmin_email_enc or not self.garmin_password_enc:
            return None
        try:
            return decrypt(self.garmin_email_enc), decrypt(self.garmin_password_enc)
        except Exception as exc:
            raise ServiceError(
                "Stored Garmin credentials could not be decrypted.",
                status_code=500,
                category=ErrorCategory.DB,
                event="garmin.credentials_decrypt_failed",
            ) from exc

    def session_payload(self) -> Optional[str]:
        if not self.garmin_session_enc:
            return None
        try:
            return decrypt(self.garmin_session_enc)
        except Exception as exc:
            raise ServiceError(
                "Stored Garmin session could not be decrypted.",
                status_code=500,
                category=ErrorCategory.DB,
                event="garmin.session_decrypt_failed",
            ) from exc

    def ui_summary(self) -> Dict[str, Any]:
        return {
            "connected": bool(self.garmin_email_enc and self.garmin_password_enc),
            "sync_status": self.sync_status,
            "sync_error": self.sync_error,
            "last_sync_at": self.last_sync_at,
        }


class GarminSessionStore:
    _select_columns = (
        "user_id,garmin_email_enc,garmin_password_enc,garmin_session_enc,"
        "garmin_session_version,garmin_account_key,garmin_account_key_source,garmin_login_key,"
        "sync_status,sync_error,last_sync_at,garmin_session_updated_at"
    )
    _legacy_select_columns = "user_id,garmin_email_enc,garmin_password_enc,sync_status,sync_error,last_sync_at"
    _ownership_scan_columns = (
        "user_id,garmin_email_enc,garmin_password_enc,"
        "garmin_account_key,garmin_account_key_source,garmin_login_key"
    )

    def __init__(self, supabase_client: Any):
        self._supabase = supabase_client
        self._logger = get_logger(__name__)
        self._session_columns_available: Optional[bool] = None

    def fetch_account(self, user_id: str) -> Optional[GarminAccount]:
        try:
            response = self._fetch_account_response(
                user_id,
                include_session_columns=self._session_columns_available is not False,
            )
        except Exception as exc:
            if self._is_missing_session_column_error(exc):
                self._mark_session_columns_unavailable(user_id, exc)
                try:
                    response = self._fetch_account_response(user_id, include_session_columns=False)
                except Exception as fallback_exc:
                    log_exception(
                        self._logger,
                        category=ErrorCategory.DB,
                        event="garmin.account_fetch_failed",
                        message="Failed to fetch Garmin account.",
                        exc=fallback_exc,
                        user_id=user_id,
                    )
                    raise ServiceError(
                        "Failed to load Garmin account.",
                        status_code=500,
                        category=ErrorCategory.DB,
                        event="garmin.account_fetch_failed",
                        context={"user_id": user_id},
                    ) from fallback_exc
            else:
                log_exception(
                    self._logger,
                    category=ErrorCategory.DB,
                    event="garmin.account_fetch_failed",
                    message="Failed to fetch Garmin account.",
                    exc=exc,
                    user_id=user_id,
                )
                raise ServiceError(
                    "Failed to load Garmin account.",
                    status_code=500,
                    category=ErrorCategory.DB,
                    event="garmin.account_fetch_failed",
                    context={"user_id": user_id},
                ) from exc

        if not response.data:
            return None
        return GarminAccount.from_row(response.data[0])

    def save_connected_account(
        self,
        user_id: str,
        email: str,
        password: str,
        session_payload: str,
        *,
        garmin_account_key: Optional[str] = None,
        garmin_account_key_source: Optional[str] = None,
        garmin_login_key: Optional[str] = None,
    ) -> GarminAccount:
        fields = {
            "garmin_email_enc": encrypt(email),
            "garmin_password_enc": encrypt(password),
            "garmin_session_enc": encrypt(session_payload),
            "garmin_account_key": garmin_account_key,
            "garmin_account_key_source": garmin_account_key_source,
            "garmin_login_key": garmin_login_key,
            "sync_status": "connected",
            "sync_error": None,
            "garmin_session_updated_at": self._utc_now(),
        }
        return self._write_versioned_account(user_id, fields)

    def find_conflicting_account(
        self,
        *,
        user_id: str,
        garmin_account_key: Optional[str],
        garmin_login_key: Optional[str],
    ) -> Optional[GarminAccount]:
        if garmin_account_key:
            owner = self._fetch_account_by_field("garmin_account_key", garmin_account_key)
            if owner is not None and owner.user_id != user_id:
                return owner

        if garmin_login_key:
            owner = self._fetch_account_by_field("garmin_login_key", garmin_login_key)
            if owner is not None and owner.user_id != user_id:
                return owner

            legacy_owner = self._find_legacy_login_conflict(user_id=user_id, garmin_login_key=garmin_login_key)
            if legacy_owner is not None and legacy_owner.user_id != user_id:
                return legacy_owner

        return None

    def save_session_atomically(self, user_id: str, session_payload: str, *, expected_version: Optional[int] = None) -> GarminAccount:
        fields = {
            "garmin_session_enc": encrypt(session_payload),
            "garmin_session_updated_at": self._utc_now(),
        }
        return self._write_versioned_account(user_id, fields, expected_version=expected_version)

    def clear_session(self, user_id: str) -> None:
        account = self.fetch_account(user_id)
        if not account:
            return

        self._write_versioned_account(
            user_id,
            {
                "garmin_session_enc": None,
                "garmin_session_updated_at": self._utc_now(),
            },
            expected_version=account.garmin_session_version,
        )

    def mark_sync_state(
        self,
        user_id: str,
        *,
        sync_status: Optional[str] = None,
        sync_error: Optional[str] = None,
        last_sync_at: Optional[str] = None,
    ) -> None:
        updates: Dict[str, Any] = {}
        if sync_status is not None:
            updates["sync_status"] = sync_status
        if sync_error is not None or sync_status == "ok":
            updates["sync_error"] = sync_error
        if last_sync_at is not None:
            updates["last_sync_at"] = last_sync_at

        if not updates:
            return

        try:
            (
                self._supabase.table(TABLE_NAME)
                .update(updates)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:
            log_exception(
                self._logger,
                category=ErrorCategory.DB,
                event="garmin.sync_state_update_failed",
                message="Failed to update Garmin sync state.",
                exc=exc,
                user_id=user_id,
                updates=list(updates.keys()),
            )
            raise ServiceError(
                "Failed to update Garmin sync state.",
                status_code=500,
                category=ErrorCategory.DB,
                event="garmin.sync_state_update_failed",
                context={"user_id": user_id},
            ) from exc

    def _write_versioned_account(
        self,
        user_id: str,
        fields: Dict[str, Any],
        *,
        expected_version: Optional[int] = None,
        max_retries: int = 4,
    ) -> GarminAccount:
        current_version = expected_version

        for attempt in range(1, max_retries + 1):
            account = self.fetch_account(user_id)
            if self._session_columns_available is False:
                return self._write_legacy_account(user_id, fields, existing_account=account)

            if account is None:
                try:
                    (
                        self._supabase.table(TABLE_NAME)
                        .upsert(
                            {
                                "user_id": user_id,
                                "garmin_session_version": 1,
                                **fields,
                            },
                            on_conflict="user_id",
                        )
                        .execute()
                    )
                    inserted = self.fetch_account(user_id)
                    if inserted is not None:
                        return inserted
                except Exception as exc:
                    if self._is_ownership_conflict_error(exc):
                        raise self._ownership_conflict_service_error() from exc
                    log_exception(
                        self._logger,
                        category=ErrorCategory.DB,
                        event="garmin.account_insert_failed",
                        message="Failed to insert Garmin account.",
                        exc=exc,
                        user_id=user_id,
                    )
                    raise ServiceError(
                        "Failed to store Garmin account.",
                        status_code=500,
                        category=ErrorCategory.DB,
                        event="garmin.account_insert_failed",
                        context={"user_id": user_id},
                    ) from exc

            account = account or self.fetch_account(user_id)
            if account is None:
                continue

            version_to_match = account.garmin_session_version if current_version is None else current_version
            next_version = version_to_match + 1

            try:
                response = (
                    self._supabase.table(TABLE_NAME)
                    .update({**fields, "garmin_session_version": next_version})
                    .eq("user_id", user_id)
                    .eq("garmin_session_version", version_to_match)
                    .execute()
                )
            except Exception as exc:
                if self._is_ownership_conflict_error(exc):
                    raise self._ownership_conflict_service_error() from exc
                log_exception(
                    self._logger,
                    category=ErrorCategory.DB,
                    event="garmin.account_update_failed",
                    message="Failed to update Garmin account.",
                    exc=exc,
                    user_id=user_id,
                    expected_version=version_to_match,
                )
                raise ServiceError(
                    "Failed to update Garmin account.",
                    status_code=500,
                    category=ErrorCategory.DB,
                    event="garmin.account_update_failed",
                    context={"user_id": user_id},
                ) from exc

            if response.data:
                return GarminAccount.from_row(response.data[0])

            latest = self.fetch_account(user_id)
            current_version = latest.garmin_session_version if latest else None
            log_event(
                self._logger,
                logging.WARNING,
                category=ErrorCategory.DB,
                event="garmin.account_conflict_retry",
                message="Garmin account update conflict, retrying.",
                user_id=user_id,
                attempt=attempt,
            )

        raise ServiceError(
            "Concurrent Garmin session update failed.",
            status_code=409,
            category=ErrorCategory.DB,
            event="garmin.account_conflict",
            context={"user_id": user_id},
        )

    def _fetch_account_response(self, user_id: str, *, include_session_columns: bool):
        columns = self._select_columns if include_session_columns else self._legacy_select_columns
        return (
            self._supabase.table(TABLE_NAME)
            .select(columns)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

    def _write_legacy_account(
        self,
        user_id: str,
        fields: Dict[str, Any],
        *,
        existing_account: Optional[GarminAccount] = None,
    ) -> GarminAccount:
        legacy_fields = {
            key: value
            for key, value in fields.items()
            if key not in SESSION_COLUMNS and key not in OWNERSHIP_COLUMNS
        }
        if not legacy_fields:
            return existing_account or self.fetch_account(user_id) or GarminAccount(user_id=user_id)

        try:
            (
                self._supabase.table(TABLE_NAME)
                .upsert({"user_id": user_id, **legacy_fields}, on_conflict="user_id")
                .execute()
            )
        except Exception as exc:
            log_exception(
                self._logger,
                category=ErrorCategory.DB,
                event="garmin.account_insert_failed",
                message="Failed to insert Garmin account.",
                exc=exc,
                user_id=user_id,
            )
            raise ServiceError(
                "Failed to store Garmin account.",
                status_code=500,
                category=ErrorCategory.DB,
                event="garmin.account_insert_failed",
                context={"user_id": user_id},
            ) from exc

        return self.fetch_account(user_id) or GarminAccount(user_id=user_id, **legacy_fields)

    def _fetch_account_by_field(self, field: str, value: str) -> Optional[GarminAccount]:
        try:
            response = (
                self._supabase.table(TABLE_NAME)
                .select(self._select_columns)
                .eq(field, value)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            log_exception(
                self._logger,
                category=ErrorCategory.DB,
                event="garmin.account_fetch_failed",
                message="Failed to fetch Garmin account by ownership field.",
                exc=exc,
                field=field,
            )
            raise ServiceError(
                "Failed to verify Garmin account ownership.",
                status_code=500,
                category=ErrorCategory.DB,
                event="garmin.account_fetch_failed",
                context={"field": field},
            ) from exc

        if not response.data:
            return None
        return GarminAccount.from_row(response.data[0])

    def _find_legacy_login_conflict(self, *, user_id: str, garmin_login_key: str) -> Optional[GarminAccount]:
        try:
            response = self._supabase.table(TABLE_NAME).select(self._ownership_scan_columns).execute()
        except Exception as exc:
            log_exception(
                self._logger,
                category=ErrorCategory.DB,
                event="garmin.account_fetch_failed",
                message="Failed to scan Garmin account ownership.",
                exc=exc,
                user_id=user_id,
            )
            raise ServiceError(
                "Failed to verify Garmin account ownership.",
                status_code=500,
                category=ErrorCategory.DB,
                event="garmin.account_fetch_failed",
                context={"user_id": user_id},
            ) from exc

        for row in response.data or []:
            account = GarminAccount.from_row(row)
            if account.user_id == user_id:
                continue
            if account.garmin_account_key or account.garmin_login_key:
                continue

            try:
                if not account.garmin_email_enc:
                    continue
                legacy_login_key = normalize_garmin_login(decrypt(account.garmin_email_enc))
            except Exception:
                continue
            if legacy_login_key and legacy_login_key == garmin_login_key:
                return account
        return None

    def _is_missing_session_column_error(self, exc: Exception) -> bool:
        message = " ".join(
            [
                str(getattr(exc, "message", "") or ""),
                str(getattr(exc, "details", "") or ""),
                str(exc),
            ]
        ).lower()
        code = str(getattr(exc, "code", "") or "")
        mentions_session_column = any(column in message for column in SESSION_COLUMNS)
        missing_column = code == "42703" or ("column" in message and "does not exist" in message)
        return mentions_session_column and missing_column

    def _is_ownership_conflict_error(self, exc: Exception) -> bool:
        code = str(getattr(exc, "code", "") or "")
        message = " ".join(
            [
                str(getattr(exc, "message", "") or ""),
                str(getattr(exc, "details", "") or ""),
                str(exc),
            ]
        ).lower()
        unique_violation = code == "23505" or "duplicate key" in message or "unique constraint" in message
        mentions_ownership_key = any(
            token in message
            for token in (
                "garmin_account_key",
                "garmin_login_key",
                "user_garmin_accounts_garmin_account_key",
                "user_garmin_accounts_garmin_login_key",
            )
        )
        return unique_violation and mentions_ownership_key

    @staticmethod
    def _ownership_conflict_service_error() -> ServiceError:
        return ServiceError(
            "This Garmin account is already connected to another account.",
            status_code=409,
            category=ErrorCategory.AUTH,
            event="garmin.account_already_linked",
        )

    def _mark_session_columns_unavailable(self, user_id: str, exc: Exception) -> None:
        if self._session_columns_available is False:
            return

        self._session_columns_available = False
        log_event(
            self._logger,
            logging.WARNING,
            category=ErrorCategory.DB,
            event="garmin.session_columns_unavailable",
            message="Garmin session columns missing; falling back to credential-only storage.",
            user_id=user_id,
            error_code=str(getattr(exc, "code", "") or ""),
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
