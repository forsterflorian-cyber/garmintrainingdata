-- =============================================================================
-- SECURITY HARDENING MIGRATION
-- Date: 2026-03-21
-- Description: Adds Row Level Security (RLS) policies and security constraints
-- =============================================================================

-- 1. Enable RLS on all tables
ALTER TABLE public.user_garmin_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_status ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.training_days ENABLE ROW LEVEL SECURITY;

-- 2. Drop existing policies if they exist (idempotent)
DROP POLICY IF EXISTS "Users can only access their own Garmin accounts" ON public.user_garmin_accounts;
DROP POLICY IF EXISTS "Users can only view their own Garmin accounts" ON public.user_garmin_accounts;
DROP POLICY IF EXISTS "Users can only update their own Garmin accounts" ON public.user_garmin_accounts;
DROP POLICY IF EXISTS "Users can only insert their own Garmin accounts" ON public.user_garmin_accounts;
DROP POLICY IF EXISTS "Users can only delete their own Garmin accounts" ON public.user_garmin_accounts;

DROP POLICY IF EXISTS "Users can only access their own sync status" ON public.sync_status;
DROP POLICY IF EXISTS "Users can only view their own sync status" ON public.sync_status;
DROP POLICY IF EXISTS "Users can only update their own sync status" ON public.sync_status;
DROP POLICY IF EXISTS "Users can only insert their own sync status" ON public.sync_status;
DROP POLICY IF EXISTS "Users can only delete their own sync status" ON public.sync_status;

DROP POLICY IF EXISTS "Users can only access their own sync runs" ON public.sync_runs;
DROP POLICY IF EXISTS "Users can only view their own sync runs" ON public.sync_runs;
DROP POLICY IF EXISTS "Users can only insert their own sync runs" ON public.sync_runs;
DROP POLICY IF EXISTS "Users can only update their own sync runs" ON public.sync_runs;
DROP POLICY IF EXISTS "Users can only delete their own sync runs" ON public.sync_runs;

DROP POLICY IF EXISTS "Users can only access their own training days" ON public.training_days;
DROP POLICY IF EXISTS "Users can only view their own training days" ON public.training_days;
DROP POLICY IF EXISTS "Users can only insert their own training days" ON public.training_days;
DROP POLICY IF EXISTS "Users can only update their own training days" ON public.training_days;
DROP POLICY IF EXISTS "Users can only delete their own training days" ON public.training_days;

-- 3. Create RLS policies for user_garmin_accounts
CREATE POLICY "Users can only view their own Garmin accounts"
ON public.user_garmin_accounts
FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can only insert their own Garmin accounts"
ON public.user_garmin_accounts
FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only update their own Garmin accounts"
ON public.user_garmin_accounts
FOR UPDATE
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only delete their own Garmin accounts"
ON public.user_garmin_accounts
FOR DELETE
USING (auth.uid() = user_id);

-- 4. Create RLS policies for sync_status
CREATE POLICY "Users can only view their own sync status"
ON public.sync_status
FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can only insert their own sync status"
ON public.sync_status
FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only update their own sync status"
ON public.sync_status
FOR UPDATE
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only delete their own sync status"
ON public.sync_status
FOR DELETE
USING (auth.uid() = user_id);

-- 5. Create RLS policies for sync_runs
CREATE POLICY "Users can only view their own sync runs"
ON public.sync_runs
FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can only insert their own sync runs"
ON public.sync_runs
FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only update their own sync runs"
ON public.sync_runs
FOR UPDATE
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only delete their own sync runs"
ON public.sync_runs
FOR DELETE
USING (auth.uid() = user_id);

-- 6. Create RLS policies for training_days
CREATE POLICY "Users can only view their own training days"
ON public.training_days
FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can only insert their own training days"
ON public.training_days
FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only update their own training days"
ON public.training_days
FOR UPDATE
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can only delete their own training days"
ON public.training_days
FOR DELETE
USING (auth.uid() = user_id);

-- 7. Skip check constraints for UUID fields
-- UUIDs are always valid by definition, RLS policies enforce user_id correctness
-- No additional constraints needed as RLS ensures data isolation

-- 8. Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_garmin_accounts_user_id 
  ON public.user_garmin_accounts (user_id);

CREATE INDEX IF NOT EXISTS idx_sync_status_user_id 
  ON public.sync_status (user_id);

CREATE INDEX IF NOT EXISTS idx_sync_runs_user_id 
  ON public.sync_runs (user_id);

CREATE INDEX IF NOT EXISTS idx_training_days_user_id 
  ON public.training_days (user_id);

CREATE INDEX IF NOT EXISTS idx_training_days_user_date 
  ON public.training_days (user_id, date);

-- 9. Add audit columns if they don't exist
ALTER TABLE public.user_garmin_accounts 
  ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

ALTER TABLE public.sync_status 
  ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

ALTER TABLE public.sync_runs 
  ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

ALTER TABLE public.training_days 
  ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

-- 10. Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 11. Create triggers for updated_at
DROP TRIGGER IF EXISTS update_user_garmin_accounts_updated_at ON public.user_garmin_accounts;
CREATE TRIGGER update_user_garmin_accounts_updated_at
    BEFORE UPDATE ON public.user_garmin_accounts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_sync_status_updated_at ON public.sync_status;
CREATE TRIGGER update_sync_status_updated_at
    BEFORE UPDATE ON public.sync_status
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_sync_runs_updated_at ON public.sync_runs;
CREATE TRIGGER update_sync_runs_updated_at
    BEFORE UPDATE ON public.sync_runs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_training_days_updated_at ON public.training_days;
CREATE TRIGGER update_training_days_updated_at
    BEFORE UPDATE ON public.training_days
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 12. Grant necessary permissions
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- 13. Add comment for documentation
COMMENT ON TABLE public.user_garmin_accounts IS 'Stores Garmin account credentials and session data for authenticated users. RLS enabled.';
COMMENT ON TABLE public.sync_status IS 'Tracks synchronization status and locks. RLS enabled.';
COMMENT ON TABLE public.sync_runs IS 'Logs synchronization runs and results. RLS enabled.';
COMMENT ON TABLE public.training_days IS 'Stores training data and recommendations. RLS enabled.';