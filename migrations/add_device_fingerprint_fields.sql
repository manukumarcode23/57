-- Add device fingerprint and detection fields to publisher_registrations table
ALTER TABLE publisher_registrations 
ADD COLUMN IF NOT EXISTS device_fingerprint VARCHAR(64),
ADD COLUMN IF NOT EXISTS device_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS device_name VARCHAR(100),
ADD COLUMN IF NOT EXISTS operating_system VARCHAR(100),
ADD COLUMN IF NOT EXISTS browser_name VARCHAR(50),
ADD COLUMN IF NOT EXISTS browser_version VARCHAR(50);

-- Add device fingerprint and detection fields to publisher_login_events table
ALTER TABLE publisher_login_events 
ADD COLUMN IF NOT EXISTS device_fingerprint VARCHAR(64),
ADD COLUMN IF NOT EXISTS device_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS device_name VARCHAR(100),
ADD COLUMN IF NOT EXISTS operating_system VARCHAR(100),
ADD COLUMN IF NOT EXISTS browser_name VARCHAR(50),
ADD COLUMN IF NOT EXISTS browser_version VARCHAR(50);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_registration_fingerprint ON publisher_registrations(device_fingerprint, created_at);
CREATE INDEX IF NOT EXISTS idx_login_fingerprint ON publisher_login_events(device_fingerprint, created_at);

-- Add comments
COMMENT ON COLUMN publisher_registrations.device_fingerprint IS 'Unique device identifier hash for tracking multi-account detection';
COMMENT ON COLUMN publisher_registrations.device_type IS 'Device type: Android, PC, Laptop, Tablet, Emulator, etc.';
COMMENT ON COLUMN publisher_registrations.device_name IS 'Specific device model or brand name';
COMMENT ON COLUMN publisher_registrations.operating_system IS 'Operating system name and version';
COMMENT ON COLUMN publisher_registrations.browser_name IS 'Browser name (Chrome, Firefox, Safari, etc.)';
COMMENT ON COLUMN publisher_registrations.browser_version IS 'Browser version number';

COMMENT ON COLUMN publisher_login_events.device_fingerprint IS 'Unique device identifier hash for tracking multi-account detection';
COMMENT ON COLUMN publisher_login_events.device_type IS 'Device type: Android, PC, Laptop, Tablet, Emulator, etc.';
COMMENT ON COLUMN publisher_login_events.device_name IS 'Specific device model or brand name';
COMMENT ON COLUMN publisher_login_events.operating_system IS 'Operating system name and version';
COMMENT ON COLUMN publisher_login_events.browser_name IS 'Browser name (Chrome, Firefox, Safari, etc.)';
COMMENT ON COLUMN publisher_login_events.browser_version IS 'Browser version number';
