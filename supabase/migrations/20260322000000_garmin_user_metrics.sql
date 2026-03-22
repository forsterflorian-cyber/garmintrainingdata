-- =============================================================================
-- GARMIN USER METRICS MIGRATION
-- Date: 2026-03-22
-- Description: Adds tracking for Garmin-synced user metrics (LTHR, FTP, etc.)
-- =============================================================================

-- 1. Drop old columns if they exist (cleanup from previous attempts)
DO $$ 
BEGIN
    -- Drop all potentially conflicting columns
    ALTER TABLE public.user_profiles DROP COLUMN IF EXISTS lthr_source;
    ALTER TABLE public.user_profiles DROP COLUMN IF EXISTS lthr_synced_at;
    ALTER TABLE public.user_profiles DROP COLUMN IF EXISTS ftp_source;
    ALTER TABLE public.user_profiles DROP COLUMN IF EXISTS ftp_synced_at;
    ALTER TABLE public.user_profiles DROP COLUMN IF EXISTS garmin_training_readiness;
    ALTER TABLE public.user_profiles DROP COLUMN IF EXISTS garmin_training_status;
    ALTER TABLE public.user_profiles DROP COLUMN IF EXISTS garmin_metrics_synced_at;
EXCEPTION
    WHEN OTHERS THEN
        -- Ignore errors during cleanup
        NULL;
END $$;

-- 2. Add Garmin sync tracking columns to user_profiles (only if they don't exist)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_profiles' AND column_name = 'lthr_source') THEN
        ALTER TABLE public.user_profiles ADD COLUMN lthr_source TEXT CHECK (lthr_source IN ('garmin', 'manual', 'estimated'));
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_profiles' AND column_name = 'lthr_synced_at') THEN
        ALTER TABLE public.user_profiles ADD COLUMN lthr_synced_at TIMESTAMPTZ;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_profiles' AND column_name = 'ftp_source') THEN
        ALTER TABLE public.user_profiles ADD COLUMN ftp_source TEXT CHECK (ftp_source IN ('garmin', 'manual', 'estimated'));
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_profiles' AND column_name = 'ftp_synced_at') THEN
        ALTER TABLE public.user_profiles ADD COLUMN ftp_synced_at TIMESTAMPTZ;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_profiles' AND column_name = 'garmin_training_readiness') THEN
        ALTER TABLE public.user_profiles ADD COLUMN garmin_training_readiness INTEGER CHECK (garmin_training_readiness >= 0 AND garmin_training_readiness <= 100);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_profiles' AND column_name = 'garmin_training_status') THEN
        ALTER TABLE public.user_profiles ADD COLUMN garmin_training_status TEXT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'user_profiles' AND column_name = 'garmin_metrics_synced_at') THEN
        ALTER TABLE public.user_profiles ADD COLUMN garmin_metrics_synced_at TIMESTAMPTZ;
    END IF;
END $$;

-- 3. Add comments
COMMENT ON COLUMN public.user_profiles.lthr_source IS 'Source of LTHR value: garmin (synced), manual (user-entered), estimated (calculated from activities)';
COMMENT ON COLUMN public.user_profiles.lthr_synced_at IS 'Timestamp when LTHR was last synced from Garmin';
COMMENT ON COLUMN public.user_profiles.ftp_source IS 'Source of FTP value: garmin (synced), manual (user-entered), estimated (calculated from activities)';
COMMENT ON COLUMN public.user_profiles.ftp_synced_at IS 'Timestamp when FTP was last synced from Garmin';
COMMENT ON COLUMN public.user_profiles.garmin_training_readiness IS 'Latest training readiness score from Garmin (0-100)';
COMMENT ON COLUMN public.user_profiles.garmin_training_status IS 'Latest training status from Garmin (e.g., PRODUCTIVE, MAINTAINING, PEAKING, etc.)';
COMMENT ON COLUMN public.user_profiles.garmin_metrics_synced_at IS 'Timestamp when Garmin metrics were last synced';
