-- =============================================================================
-- USER PROFILES MIGRATION
-- Date: 2026-03-21
-- Description: Adds user profiles for personalized training metrics
-- =============================================================================

-- 1. Create user_profiles table
CREATE TABLE IF NOT EXISTS public.user_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Basis-Daten
    age INTEGER CHECK (age > 0 AND age < 120),
    weight_kg FLOAT CHECK (weight_kg > 0 AND weight_kg < 500),
    height_cm FLOAT CHECK (height_cm > 0 AND height_cm < 300),
    gender TEXT CHECK (gender IN ('male', 'female', 'other')),
    
    -- Heart Rate
    max_hr INTEGER CHECK (max_hr > 0 AND max_hr < 250),
    resting_hr INTEGER CHECK (resting_hr > 0 AND resting_hr < 120),
    lthr INTEGER CHECK (lthr > 0 AND lthr < 250),  -- Lactate Threshold Heart Rate
    
    -- Power (Cycling)
    ftp FLOAT CHECK (ftp > 0 AND ftp < 2000),  -- Functional Threshold Power
    critical_power FLOAT CHECK (critical_power > 0 AND critical_power < 2000),
    
    -- Pace (Running)
    critical_pace FLOAT CHECK (critical_pace > 0 AND critical_pace < 20),  -- min/km
    vdot FLOAT CHECK (vdot > 0 AND vdot < 100),  -- VDOT Score
    
    -- Training Preferences
    sport_focus TEXT CHECK (sport_focus IN ('run', 'bike', 'strength', 'hybrid')),
    weekly_volume_target INTEGER CHECK (weekly_volume_target > 0),  -- Minuten
    intensity_preference TEXT CHECK (intensity_preference IN ('low', 'moderate', 'high')),
    
    -- Goals
    race_date DATE,
    race_distance TEXT,
    race_goal_time INTERVAL,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Enable RLS
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

-- 3. Drop existing policies if they exist
DROP POLICY IF EXISTS "Users can view their own profile" ON public.user_profiles;
DROP POLICY IF EXISTS "Users can insert their own profile" ON public.user_profiles;
DROP POLICY IF EXISTS "Users can update their own profile" ON public.user_profiles;
DROP POLICY IF EXISTS "Users can delete their own profile" ON public.user_profiles;

-- 4. Create RLS policies
CREATE POLICY "Users can view their own profile"
ON public.user_profiles
FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own profile"
ON public.user_profiles
FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own profile"
ON public.user_profiles
FOR UPDATE
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own profile"
ON public.user_profiles
FOR DELETE
USING (auth.uid() = user_id);

-- 5. Create indexes
CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id 
    ON public.user_profiles (user_id);

CREATE INDEX IF NOT EXISTS idx_user_profiles_sport_focus 
    ON public.user_profiles (sport_focus);

-- 6. Create updated_at trigger
DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON public.user_profiles;

CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 7. Add comments
COMMENT ON TABLE public.user_profiles IS 'User profiles for personalized training metrics and preferences. RLS enabled.';
COMMENT ON COLUMN public.user_profiles.ftp IS 'Functional Threshold Power in Watt (Cycling)';
COMMENT ON COLUMN public.user_profiles.critical_pace IS 'Critical Pace in min/km (Running)';
COMMENT ON COLUMN public.user_profiles.lthr IS 'Lactate Threshold Heart Rate in bpm';
COMMENT ON COLUMN public.user_profiles.vdot IS 'VDOT Score for running performance prediction';