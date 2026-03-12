from __future__ import annotations

import os
from typing import Iterable, List


SERVER_REQUIRED_ENV_VARS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "APP_SECRET_KEY",
)


def missing_env_vars(names: Iterable[str]) -> List[str]:
    missing: List[str] = []
    for name in names:
        value = os.environ.get(name, "")
        if not str(value).strip():
            missing.append(name)
    return missing


def require_env(name: str, *, context: str) -> str:
    value = str(os.environ.get(name, "")).strip()
    if value:
        return value
    raise RuntimeError(
        f"{name} is required for {context}. Copy .env.example, set the missing value, and restart the app."
    )


def assert_required_env(names: Iterable[str], *, context: str) -> None:
    missing = missing_env_vars(names)
    if not missing:
        return
    joined = ", ".join(missing)
    raise RuntimeError(
        f"Missing required environment variables for {context}: {joined}. "
        "Copy .env.example, set the missing values, and restart the app."
    )


def validate_server_runtime() -> None:
    assert_required_env(SERVER_REQUIRED_ENV_VARS, context="application startup")
