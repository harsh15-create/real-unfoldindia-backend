-- 1. Update profiles table with new fields
-- We use 'alter table' to add columns if they don't exist.
-- Note: 'travel_style' was previously text, we might want to change it to text[] or just handle it as a comma-separated string in frontend.
-- For this plan, let's assume we keep it simple or migrate. If it's already text, we can add new array columns.

ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS preferred_regions text[],
ADD COLUMN IF NOT EXISTS interests text[];

-- 2. Create user_exploration_events table
CREATE TABLE IF NOT EXISTS user_exploration_events (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
  entity_type text NOT NULL CHECK (entity_type IN ('city', 'state', 'region')),
  entity_id text NOT NULL, -- Can be a slug or UUID
  signal_type text NOT NULL CHECK (signal_type IN ('view', 'save', 'trip', 'route', 'ai')),
  weight int NOT NULL DEFAULT 1,
  created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS for exploration events
ALTER TABLE user_exploration_events ENABLE ROW LEVEL SECURITY;

-- Policy: Users can insert their own events
CREATE POLICY "Users can insert their own exploration events" 
ON user_exploration_events FOR INSERT 
WITH CHECK (auth.uid() = user_id);

-- Policy: Users can view their own events
CREATE POLICY "Users can view their own exploration events" 
ON user_exploration_events FOR SELECT 
USING (auth.uid() = user_id);

-- 3. Create user_badges table
CREATE TABLE IF NOT EXISTS user_badges (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
  badge_id text NOT NULL, -- e.g., 'first_step', 'north_explorer'
  unlocked_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
  UNIQUE(user_id, badge_id) -- Prevent duplicate badges
);

-- Enable RLS for badges
ALTER TABLE user_badges ENABLE ROW LEVEL SECURITY;

-- Policy: Users can view their own badges
CREATE POLICY "Users can view their own badges" 
ON user_badges FOR SELECT 
USING (auth.uid() = user_id);

-- Policy: System/Functions can insert badges (but for client-side logic, we might allow insert if we trust the client logic, 
-- ideally this is done via Edge Function, but for now we allow insert with check)
CREATE POLICY "Users can insert their own badges" 
ON user_badges FOR INSERT 
WITH CHECK (auth.uid() = user_id);

-- 4. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_exploration_user_entity ON user_exploration_events(user_id, entity_id);
CREATE INDEX IF NOT EXISTS idx_badges_user ON user_badges(user_id);

-- 5. Create user_progress_insights table (AI Cache)
CREATE TABLE IF NOT EXISTS user_progress_insights (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id uuid REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
  insight_type text NOT NULL CHECK (insight_type IN ('summary', 'challenge', 'reflection')),
  input_hash text NOT NULL, -- To prevent re-generating for same state
  output_text text NOT NULL,
  generated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS for insights
ALTER TABLE user_progress_insights ENABLE ROW LEVEL SECURITY;

-- Policy: Users can view their own insights
CREATE POLICY "Users can view their own insights" 
ON user_progress_insights FOR SELECT 
USING (auth.uid() = user_id);

-- Policy: Service role (Edge Function) can insert insights
-- (Users generally shouldn't insert their own insights directly, but for simplicity in some setups we might allow it. 
-- Ideally, this is strictly server-side.)
CREATE POLICY "Users can insert their own insights" 
ON user_progress_insights FOR INSERT 
WITH CHECK (auth.uid() = user_id);
