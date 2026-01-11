-- Add hardware_fingerprint field to publisher_registrations table
-- This field stores hardware-only device fingerprints for cross-IP detection
ALTER TABLE publisher_registrations 
ADD COLUMN IF NOT EXISTS hardware_fingerprint VARCHAR(64);

-- Add index for hardware fingerprint queries
CREATE INDEX IF NOT EXISTS idx_registration_hardware_fingerprint 
ON publisher_registrations(hardware_fingerprint, created_at);

-- Add hardware_fingerprint field to publisher_login_events table
ALTER TABLE publisher_login_events 
ADD COLUMN IF NOT EXISTS hardware_fingerprint VARCHAR(64);

-- Add index for hardware fingerprint queries
CREATE INDEX IF NOT EXISTS idx_login_hardware_fingerprint 
ON publisher_login_events(hardware_fingerprint, created_at);

-- Note: This migration adds hardware-specific device fingerprints that persist
-- across IP/network changes, enabling detection of same-device multi-account abuse
-- even when users switch networks or use VPNs.
