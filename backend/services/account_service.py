from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, Tuple
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from backend.services.sync_status_service import SYNC_RUNS_TABLE, SYNC_STATUS_TABLE
from observability import ErrorCategory, ServiceError, get_logger, log_event, log_exception


GARMIN_ACCOUNTS_TABLE = "user_garmin_accounts"
TRAINING_DAYS_TABLE = "training_days"
ACCOUNT_DELETE_REDIRECT = "/auth"
DELETE_CONFIRMATION_TEXT = "DELETE"
USER_SCOPED_DELETE_ORDER: Tuple[Tuple[str, str], ...] = (
    ("garmin_account", GARMIN_ACCOUNTS_TABLE),
    ("sync_runs", SYNC_RUNS_TABLE),
    ("sync_status", SYNC_STATUS_TABLE),
    ("training_days", TRAINING_DAYS_TABLE),
)
AUTH_DELETE_PATHS: Tuple[str, ...] = (
    "/auth/v1/admin/user/{user_id}",
    "/auth/v1/admin/users/{user_id}",
)


def validate_account_deletion_confirmation(confirmation_text: str | None) -> str:
    normalized = str(confirmation_text or "").strip()
    if normalized != DELETE_CONFIRMATION_TEXT:
        raise ServiceError(
            "Type DELETE to confirm account deletion.",
            status_code=400,
            category=ErrorCategory.AUTH,
            event="account.delete_invalid_confirmation",
        )
    return normalized


class AccountService:
    def __init__(
        self,
        supabase_client: Any,
        *,
        auth_user_deleter: Callable[[str], bool] | None = None,
    ) -> None:
        self._supabase = supabase_client
        self._logger = get_logger(__name__)
        self._auth_user_deleter = auth_user_deleter or self._delete_auth_user

    def delete_account(self, user_id: str, *, confirmation_text: str | None) -> Dict[str, Any]:
        validate_account_deletion_confirmation(confirmation_text)
        completed_steps = []

        try:
            for step_name, table_name in USER_SCOPED_DELETE_ORDER:
                self._delete_user_rows(table_name, user_id)
                completed_steps.append(step_name)

            auth_user_deleted = bool(self._auth_user_deleter(user_id))
            completed_steps.append("auth_user")
        except ServiceError as exc:
            log_exception(
                self._logger,
                category=exc.category,
                event=exc.event,
                message="Account deletion failed.",
                exc=exc,
                user_id=user_id,
                completed_steps=completed_steps,
            )
            raise
        except Exception as exc:
            log_exception(
                self._logger,
                category=ErrorCategory.DB,
                event="account.delete_failed",
                message="Account deletion failed.",
                exc=exc,
                user_id=user_id,
                completed_steps=completed_steps,
            )
            raise ServiceError(
                "Account deletion could not be completed. Please try again.",
                status_code=500,
                category=ErrorCategory.DB,
                event="account.delete_failed",
                context={"user_id": user_id},
            ) from exc

        log_event(
            self._logger,
            logging.INFO,
            category=ErrorCategory.AUTH,
            event="account.delete_success",
            message="Account deleted.",
            user_id=user_id,
            completed_steps=completed_steps,
            auth_user_deleted=auth_user_deleted,
        )
        return {
            "status": "deleted",
            "redirectTo": ACCOUNT_DELETE_REDIRECT,
            "signOut": True,
            "authUserDeleted": auth_user_deleted,
        }

    def _delete_user_rows(self, table_name: str, user_id: str) -> None:
        (
            self._supabase.table(table_name)
            .delete()
            .eq("user_id", user_id)
            .execute()
        )

    def _delete_auth_user(self, user_id: str) -> bool:
        admin = getattr(getattr(self._supabase, "auth", None), "admin", None)
        delete_user = getattr(admin, "delete_user", None) if admin else None
        if callable(delete_user):
            for args, kwargs in (
                ((user_id,), {}),
                ((), {"uid": user_id}),
                ((), {"user_id": user_id}),
            ):
                try:
                    delete_user(*args, **kwargs)
                    return True
                except TypeError:
                    continue
                except Exception as exc:
                    raise ServiceError(
                        "Account deletion could not be completed. Please try again.",
                        status_code=500,
                        category=ErrorCategory.AUTH,
                        event="account.auth_delete_failed",
                        context={"user_id": user_id},
                    ) from exc

        return self._delete_auth_user_via_http(user_id)

    def _delete_auth_user_via_http(self, user_id: str) -> bool:
        base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if not base_url or not service_role_key:
            raise ServiceError(
                "Account deletion could not be completed. Please try again.",
                status_code=500,
                category=ErrorCategory.AUTH,
                event="account.auth_delete_unavailable",
            )

        encoded_user_id = url_parse.quote(user_id, safe="")
        headers = {
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        }
        last_http_error: tuple[url_error.HTTPError, str] | None = None

        for path in AUTH_DELETE_PATHS:
            request = url_request.Request(
                f"{base_url}{path.format(user_id=encoded_user_id)}",
                method="DELETE",
                headers=headers,
            )
            try:
                with url_request.urlopen(request, timeout=15):
                    return True
            except url_error.HTTPError as exc:
                body = exc.read().decode("utf-8", "ignore")
                if exc.code == 404 and self._is_missing_auth_user_error(body):
                    return True
                if exc.code in {404, 405}:
                    last_http_error = (exc, body)
                    continue
                raise ServiceError(
                    "Account deletion could not be completed. Please try again.",
                    status_code=500,
                    category=ErrorCategory.AUTH,
                    event="account.auth_delete_failed",
                    context={"user_id": user_id},
                ) from exc
            except Exception as exc:
                raise ServiceError(
                    "Account deletion could not be completed. Please try again.",
                    status_code=500,
                    category=ErrorCategory.AUTH,
                    event="account.auth_delete_failed",
                    context={"user_id": user_id},
                ) from exc

        if last_http_error is not None:
            exc, _body = last_http_error
            raise ServiceError(
                "Account deletion could not be completed. Please try again.",
                status_code=500,
                category=ErrorCategory.AUTH,
                event="account.auth_delete_failed",
                context={"user_id": user_id},
            ) from exc

        return True

    @staticmethod
    def _is_missing_auth_user_error(body: str) -> bool:
        lowered = body.lower()
        return "user" in lowered and "not found" in lowered
