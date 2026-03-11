from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from observability import ErrorCategory, ServiceError


@dataclass(frozen=True)
class GarminAccountIdentity:
    garmin_account_key: str
    garmin_account_key_source: str
    garmin_login_key: str
    garmin_guid: Optional[str] = None
    profile_id: Optional[int] = None
    profile_user_id: Optional[int] = None
    user_name: Optional[str] = None
    display_name: Optional[str] = None


def normalize_garmin_login(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def resolve_garmin_account_identity(client: Any, *, login_identifier: str) -> GarminAccountIdentity:
    login_key = normalize_garmin_login(login_identifier)
    profile = _profile_payload(client)

    garmin_guid = _normalized_text(_profile_value(profile, "garmin_guid", "garminGuid"))
    profile_id = _safe_int(_profile_value(profile, "profile_id", "profileId"))
    profile_user_id = _safe_int(_profile_value(profile, "id", "userId"))
    user_name = normalize_garmin_login(_profile_value(profile, "user_name", "userName"))
    display_name = _normalized_text(
        _profile_value(profile, "display_name", "displayName")
        or getattr(client, "display_name", None)
    )

    if garmin_guid:
        return GarminAccountIdentity(
            garmin_account_key=f"garmin_guid:{garmin_guid.lower()}",
            garmin_account_key_source="garmin_guid",
            garmin_login_key=login_key,
            garmin_guid=garmin_guid,
            profile_id=profile_id,
            profile_user_id=profile_user_id,
            user_name=user_name or None,
            display_name=display_name,
        )

    if profile_id is not None:
        return GarminAccountIdentity(
            garmin_account_key=f"profile_id:{profile_id}",
            garmin_account_key_source="profile_id",
            garmin_login_key=login_key,
            garmin_guid=garmin_guid,
            profile_id=profile_id,
            profile_user_id=profile_user_id,
            user_name=user_name or None,
            display_name=display_name,
        )

    if profile_user_id is not None:
        return GarminAccountIdentity(
            garmin_account_key=f"user_id:{profile_user_id}",
            garmin_account_key_source="user_id",
            garmin_login_key=login_key,
            garmin_guid=garmin_guid,
            profile_id=profile_id,
            profile_user_id=profile_user_id,
            user_name=user_name or None,
            display_name=display_name,
        )

    if user_name:
        return GarminAccountIdentity(
            garmin_account_key=f"user_name:{user_name}",
            garmin_account_key_source="user_name",
            garmin_login_key=login_key,
            garmin_guid=garmin_guid,
            profile_id=profile_id,
            profile_user_id=profile_user_id,
            user_name=user_name,
            display_name=display_name,
        )

    if login_key:
        return GarminAccountIdentity(
            garmin_account_key=f"login:{login_key}",
            garmin_account_key_source="login",
            garmin_login_key=login_key,
            garmin_guid=garmin_guid,
            profile_id=profile_id,
            profile_user_id=profile_user_id,
            user_name=user_name or None,
            display_name=display_name,
        )

    if display_name:
        normalized_display_name = normalize_garmin_login(display_name)
        return GarminAccountIdentity(
            garmin_account_key=f"display_name:{normalized_display_name}",
            garmin_account_key_source="display_name",
            garmin_login_key=normalized_display_name,
            garmin_guid=garmin_guid,
            profile_id=profile_id,
            profile_user_id=profile_user_id,
            user_name=user_name or None,
            display_name=display_name,
        )

    raise ServiceError(
        "Garmin account identity could not be resolved.",
        status_code=500,
        category=ErrorCategory.API,
        event="garmin.identity_missing",
    )


def _profile_payload(client: Any) -> Any:
    garth_client = getattr(client, "garth", None)
    if garth_client is not None:
        profile = getattr(garth_client, "profile", None)
        if profile is not None:
            return profile
        user_profile = getattr(garth_client, "user_profile", None)
        if user_profile is not None:
            return user_profile
    return None


def _profile_value(profile: Any, snake_key: str, camel_key: str) -> Any:
    if profile is None:
        return None
    if isinstance(profile, dict):
        if snake_key in profile:
            return profile.get(snake_key)
        return profile.get(camel_key)
    if hasattr(profile, snake_key):
        return getattr(profile, snake_key)
    if hasattr(profile, camel_key):
        return getattr(profile, camel_key)
    return None


def _normalized_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
