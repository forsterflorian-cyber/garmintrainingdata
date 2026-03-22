-- =============================================================================
-- GARMIN USER METRICS MIGRATION
-- Date: 2026-03-22
-- Description: Adds tracking for Garmin-synced user metrics (LTHR, FTP, etc.)
-- =============================================================================

-- 1. Add Garmin sync tracking columns to user_profiles
ALTER TABLE public.user_profiles 
ADD COLUMN IF NOT EXISTS lthr_source TEXT CHECK (lthr_source IN ('garmin', 'manual', 'estimated')),
ADD COLUMN IF NOT EXISTS lthr_synced_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS ftp_source TEXT CHECK (ftp_source IN ('garmin', 'manual', 'estimated')),
ADD COLUMN IF NOT EXISTS ftp_synced_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS garmin_training_readiness INTEGER CHECK (garmin_training_readiness >= 0 AND garmin_training_readiness <= 100),
ADD COLUMN IF NOT EXISTS garmin_training_status TEXT,
ADD COLUMN IF NOT EXISTS garmin_metrics_synced_at TIMESTAMPTZ;

-- 2. Add comments
COMMENT ON COLUMN public.user_profiles.lthr_source IS 'Source of LTHR value: garmin (synced), manual (user-entered), estimated (calculated from activities)';
COMMENT ON COLUMN public.user_profiles.lthr_synced_at IS 'Timestamp when LTHR was last synced from Garmin';
COMMENT ON COLUMN public.user_profiles.ftp_source IS 'Source of FTP value: garmin (synced), manual (user-entered), estimated (calculated from activities)';
COMMENT ON COLUMN public.user_profiles.ftp_synced_at IS 'Timestamp when FTP was last synced from Garmin';
COMMENT ON COLUMN public.user_profiles.garmin_training_readiness IS 'Latest training readiness score from Garmin (0-100)';
COMMENT ON COLUMN public.user_profiles.garmin_training_status IS 'Latest training status from Garmin (e.g., PRODUCTIVE, MAINTAINING, PEAKING, etc.)';
COMMENT ON COLUMN public.user_profiles.garmin_metrics_synced_at IS 'Timestamp when Garmin metrics were last synced';