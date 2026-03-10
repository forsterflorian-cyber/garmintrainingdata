"""Legacy auth shim.

Routes should use bearer-token auth via Supabase, not HTTP Basic Auth.
"""

from auth_supabase import require_user, require_user as requires_auth

__all__ = ["require_user", "requires_auth"]
