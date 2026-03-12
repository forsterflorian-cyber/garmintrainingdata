from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from runtime_config import require_env


@lru_cache(maxsize=1)
def get_supabase_admin_client() -> Client:
    url = require_env("SUPABASE_URL", context="the Supabase admin client")
    service_key = require_env("SUPABASE_SERVICE_ROLE_KEY", context="the Supabase admin client")
    return create_client(url, service_key)
