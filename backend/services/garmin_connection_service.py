from __future__ import annotations

from typing import Any, Callable

from backend.services.garmin_account_identity import resolve_garmin_account_identity
from garmin_session_store import GarminAccount, GarminSessionStore
from observability import ErrorCategory, ServiceError


GARMIN_ACCOUNT_ALREADY_LINKED_MESSAGE = "This Garmin account is already connected to another account."


class GarminConnectionService:
    def __init__(
        self,
        *,
        session_store: GarminSessionStore,
        load_client_fn: Callable[..., Any],
        export_session_fn: Callable[[Any], str | None],
    ) -> None:
        self._session_store = session_store
        self._load_client = load_client_fn
        self._export_session = export_session_fn

    def connect_account(self, user_id: str, *, email: str, password: str) -> GarminAccount:
        client = self._load_client(email=email, password=password)
        identity = resolve_garmin_account_identity(client, login_identifier=email)

        conflict = self._session_store.find_conflicting_account(
            user_id=user_id,
            garmin_account_key=identity.garmin_account_key,
            garmin_login_key=identity.garmin_login_key,
        )
        if conflict is not None and conflict.user_id != user_id:
            raise garmin_account_already_linked_error()

        session_payload = self._export_session(client)
        if not session_payload:
            raise ServiceError(
                "Garmin session could not be serialized.",
                status_code=500,
                category=ErrorCategory.API,
                event="garmin.connect_session_missing",
            )

        return self._session_store.save_connected_account(
            user_id,
            email,
            password,
            session_payload,
            garmin_account_key=identity.garmin_account_key,
            garmin_account_key_source=identity.garmin_account_key_source,
            garmin_login_key=identity.garmin_login_key,
        )


def garmin_account_already_linked_error() -> ServiceError:
    return ServiceError(
        GARMIN_ACCOUNT_ALREADY_LINKED_MESSAGE,
        status_code=409,
        category=ErrorCategory.AUTH,
        event="garmin.account_already_linked",
    )
