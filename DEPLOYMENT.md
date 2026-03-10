# Deployment Notes

Run the Supabase migration before deploying the refactored app:

- [supabase/migrations/20260310_garmin_sessions.sql](/E:/Verwaltung/07_IT & Identität/IT Projekte/garmintrainingdata/supabase/migrations/20260310_garmin_sessions.sql)

Required environment variables:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET` when HS256 JWT verification is enabled
- `APP_SECRET_KEY`

The refactor stores Garmin sessions in `user_garmin_accounts.garmin_session_enc` and increments
`garmin_session_version` for optimistic, conflict-safe token refresh writes.
