# Deployment Notes

Apply the Supabase migrations before deploying:

- [`supabase/migrations/20260310_sync_status.sql`](supabase/migrations/20260310_sync_status.sql)
- [`supabase/migrations/20260310_garmin_sessions.sql`](supabase/migrations/20260310_garmin_sessions.sql)
- [`supabase/migrations/20260311_garmin_account_ownership.sql`](supabase/migrations/20260311_garmin_account_ownership.sql)

Required environment variables:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `APP_SECRET_KEY`

Optional:

- `SUPABASE_JWT_SECRET` when HS256 JWT verification is enabled
- `APP_ENV=production` to disable debug mode
- `SYNC_*` variables when you need non-default sync timing or backfill thresholds

Garmin sessions are stored in `user_garmin_accounts.garmin_session_enc`, and
`garmin_session_version` is incremented for optimistic, conflict-safe session refresh writes.
