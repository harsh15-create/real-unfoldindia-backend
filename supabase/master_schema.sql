-- MASTER SCHEMA FOR UNFOLD INDIA
-- Covers: User Identity, Chat, Privacy, Security, User Roles
-- Excludes: Exploration, Badges

-- 0. Cleanup: Remove deprecated tables if they exist
DROP TABLE IF EXISTS user_exploration_events;
DROP TABLE IF EXISTS user_badges;
DROP TABLE IF EXISTS user_progress_insights;

-- 1. Core Identity: Modify 'profiles' to match 'user_profiles' requirements
-- We do not drop profiles; we enhance it.
ALTER TABLE profiles 
ADD COLUMN IF NOT EXISTS verification_status TEXT CHECK (verification_status IN ('verified', 'pending', 'unverified')) DEFAULT 'pending',
ADD COLUMN IF NOT EXISTS last_login TIMESTAMP WITH TIME ZONE;

-- Ensure indexes exist
CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_created_at ON profiles(created_at DESC);


-- 2. Chat Module

-- Function: handle_auto_delete_messages
-- This function runs on every new message to clean up old history based on user settings.
CREATE OR REPLACE FUNCTION handle_auto_delete_messages()
RETURNS TRIGGER AS $$
DECLARE
  retention_period INTERVAL;
  setting_value TEXT;
BEGIN
  -- Get user's auto-delete setting
  SELECT auto_delete_period INTO setting_value
  FROM chat_settings
  WHERE user_id = NEW.user_id;

  -- Determine retention interval
  CASE setting_value
    WHEN 'after_1_month' THEN retention_period := INTERVAL '1 month';
    WHEN 'after_3_months' THEN retention_period := INTERVAL '3 months';
    WHEN 'after_6_months' THEN retention_period := INTERVAL '6 months';
    WHEN 'after_1_year' THEN retention_period := INTERVAL '1 year';
    ELSE retention_period := NULL; -- keep_forever or null
  END CASE;

  -- Delete old messages if a period is set
  IF retention_period IS NOT NULL THEN
    DELETE FROM chat_messages
    WHERE user_id = NEW.user_id
      AND timestamp < (NOW() - retention_period);
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Table: chat_settings
CREATE TABLE IF NOT EXISTS chat_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
  history_storage_enabled BOOLEAN DEFAULT true,
  auto_delete_period TEXT CHECK (auto_delete_period IN ('keep_forever', 'after_1_month', 'after_3_months', 'after_6_months', 'after_1_year')) DEFAULT 'keep_forever',
  sync_enabled BOOLEAN DEFAULT true,
  memory_learning_enabled BOOLEAN DEFAULT true,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_settings_user_id ON chat_settings(user_id);

-- Table: chat_messages
CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  conversation_id UUID NOT NULL,
  message_content TEXT NOT NULL,
  message_type TEXT CHECK (message_type IN ('user', 'assistant')) NOT NULL,
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  deleted_at TIMESTAMP WITH TIME ZONE,
  is_exported BOOLEAN DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id ON chat_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp DESC);

-- Trigger: Cleanup old messages on insert
DROP TRIGGER IF EXISTS trigger_cleanup_messages ON chat_messages;
CREATE TRIGGER trigger_cleanup_messages
  AFTER INSERT ON chat_messages
  FOR EACH ROW
  EXECUTE FUNCTION handle_auto_delete_messages();


-- 3. User Preferences Module

-- Table: user_preferences
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
  preferred_airlines TEXT[] DEFAULT ARRAY[]::TEXT[],
  dietary_restrictions TEXT[] DEFAULT ARRAY[]::TEXT[],
  travel_style TEXT,
  stored_memories JSONB DEFAULT '{}',
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);


-- 4. Privacy Module

-- Table: privacy_settings
CREATE TABLE IF NOT EXISTS privacy_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
  location_access_enabled BOOLEAN DEFAULT true,
  location_access_granted_at TIMESTAMP WITH TIME ZONE,
  push_notifications_enabled BOOLEAN DEFAULT true,
  push_notifications_granted_at TIMESTAMP WITH TIME ZONE,
  analytics_data_sharing_enabled BOOLEAN DEFAULT false,
  analytics_data_sharing_granted_at TIMESTAMP WITH TIME ZONE,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_privacy_settings_user_id ON privacy_settings(user_id);

-- Table: permission_audit_log
CREATE TABLE IF NOT EXISTS permission_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  permission_type TEXT CHECK (permission_type IN ('location', 'notification', 'analytics', 'data_sharing')) NOT NULL,
  action TEXT CHECK (action IN ('granted', 'revoked', 'modified')) NOT NULL,
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  ip_address INET,
  device_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_permission_audit_log_user_id ON permission_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_permission_audit_log_timestamp ON permission_audit_log(timestamp DESC);

-- Table: third_party_integrations
CREATE TABLE IF NOT EXISTS third_party_integrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  integration_name TEXT NOT NULL,
  is_connected BOOLEAN DEFAULT false,
  data_accessible BOOLEAN DEFAULT false,
  connected_at TIMESTAMP WITH TIME ZONE,
  last_accessed TIMESTAMP WITH TIME ZONE,
  UNIQUE(user_id, integration_name)
);
CREATE INDEX IF NOT EXISTS idx_third_party_integrations_user_id ON third_party_integrations(user_id);


-- 5. Security Module

-- 5. Security Module

-- Table: active_sessions
CREATE TABLE IF NOT EXISTS active_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  session_token TEXT UNIQUE NOT NULL,
  device_name TEXT,
  location TEXT,
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  is_active BOOLEAN DEFAULT true,
  is_trusted BOOLEAN DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_active_sessions_user_id ON active_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_active_sessions_expires_at ON active_sessions(expires_at);

-- Table: login_attempts
CREATE TABLE IF NOT EXISTS login_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  attempt_status TEXT CHECK (attempt_status IN ('success', 'failed', 'blocked')) NOT NULL,
  failure_reason TEXT,
  ip_address INET,
  user_agent TEXT,
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  is_suspicious BOOLEAN DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_user_id ON login_attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email);
CREATE INDEX IF NOT EXISTS idx_login_attempts_timestamp ON login_attempts(timestamp DESC);

-- Table: security_audit_log
CREATE TABLE IF NOT EXISTS security_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  event_type TEXT CHECK (event_type IN ('password_change', 'session_created', 'session_revoked', 'login_failed', 'device_added', '2fa_enabled', '2fa_disabled')) NOT NULL,
  event_details JSONB,
  ip_address INET,
  device_info TEXT,
  severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')) DEFAULT 'low',
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_security_audit_log_user_id ON security_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_security_audit_log_timestamp ON security_audit_log(timestamp DESC);


-- 6. Data Management Module

-- Table: data_export_requests
CREATE TABLE IF NOT EXISTS data_export_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  export_type TEXT CHECK (export_type IN ('chat_history_pdf', 'chat_history_json', 'all_data')) NOT NULL,
  status TEXT CHECK (status IN ('pending', 'processing', 'ready', 'expired')) DEFAULT 'pending',
  file_url TEXT,
  requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE,
  expires_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_data_export_requests_user_id ON data_export_requests(user_id);

-- Table: account_deletion_requests
CREATE TABLE IF NOT EXISTS account_deletion_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
  status TEXT CHECK (status IN ('pending_confirmation', 'confirmed', 'completed', 'cancelled')) DEFAULT 'pending_confirmation',
  confirmation_token TEXT UNIQUE,
  requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  confirmed_at TIMESTAMP WITH TIME ZONE,
  executed_at TIMESTAMP WITH TIME ZONE,
  scheduled_deletion_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_account_deletion_requests_user_id ON account_deletion_requests(user_id);


-- 7. User Roles Module

-- Table: user_roles
CREATE TABLE IF NOT EXISTS user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  role TEXT CHECK (role IN ('user', 'premium_user', 'admin', 'support_agent')) NOT NULL,
  assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);


-- 8. Row Level Security Policies

-- Enable RLS on all new tables
ALTER TABLE chat_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE privacy_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE permission_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE third_party_integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_security ENABLE ROW LEVEL SECURITY;
ALTER TABLE active_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE login_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_export_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE account_deletion_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;


-- Define Policies
-- General pattern: Users see/edit their own data.

-- Chat Settings
DROP POLICY IF EXISTS "Users can see own chat settings" ON chat_settings;
CREATE POLICY "Users can see own chat settings" ON chat_settings FOR ALL USING (auth.uid() = user_id);

-- Chat Messages
DROP POLICY IF EXISTS "Users can manage own chat messages" ON chat_messages;
CREATE POLICY "Users can manage own chat messages" ON chat_messages FOR ALL USING (auth.uid() = user_id);

-- Preferences
DROP POLICY IF EXISTS "Users can see own preferences" ON user_preferences;
CREATE POLICY "Users can see own preferences" ON user_preferences FOR ALL USING (auth.uid() = user_id);

-- Privacy
DROP POLICY IF EXISTS "Users can see own privacy settings" ON privacy_settings;
CREATE POLICY "Users can see own privacy settings" ON privacy_settings FOR ALL USING (auth.uid() = user_id);

-- Permission Audit
DROP POLICY IF EXISTS "Users can see own audit logs" ON permission_audit_log;
CREATE POLICY "Users can see own audit logs" ON permission_audit_log FOR SELECT USING (auth.uid() = user_id);

-- Integrations
DROP POLICY IF EXISTS "Users can see own integrations" ON third_party_integrations;
CREATE POLICY "Users can see own integrations" ON third_party_integrations FOR ALL USING (auth.uid() = user_id);

-- Active Sessions
DROP POLICY IF EXISTS "Users can see own sessions" ON active_sessions;
CREATE POLICY "Users can see own sessions" ON active_sessions FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can revoke own sessions" ON active_sessions;
CREATE POLICY "Users can revoke own sessions" ON active_sessions FOR UPDATE USING (auth.uid() = user_id);

-- Login Attempts
DROP POLICY IF EXISTS "Users can see own login attempts" ON login_attempts;
CREATE POLICY "Users can see own login attempts" ON login_attempts FOR SELECT USING (auth.uid() = user_id OR email = (auth.jwt() ->> 'email'));

-- Security Audit
DROP POLICY IF EXISTS "Users can see own security audit logs" ON security_audit_log;
CREATE POLICY "Users can see own security audit logs" ON security_audit_log FOR SELECT USING (auth.uid() = user_id);

-- Data Exports
DROP POLICY IF EXISTS "Users can see own export requests" ON data_export_requests;
CREATE POLICY "Users can see own export requests" ON data_export_requests FOR ALL USING (auth.uid() = user_id);

-- Deletion Requests
DROP POLICY IF EXISTS "Users can see own deletion requests" ON account_deletion_requests;
CREATE POLICY "Users can see own deletion requests" ON account_deletion_requests FOR ALL USING (auth.uid() = user_id);

-- User Roles
DROP POLICY IF EXISTS "Users can see own roles" ON user_roles;
CREATE POLICY "Users can see own roles" ON user_roles FOR SELECT USING (auth.uid() = user_id);
