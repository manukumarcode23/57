-- Migration: Initialize Settings Table with Default Values
-- Date: November 12, 2025
-- Description: Ensures Settings table has at least one row with default values
-- This prevents NULL errors when code assumes Settings table has data

-- Insert default settings if table is empty
INSERT INTO settings (
    id,
    impression_rate,
    impression_cutback_percentage,
    minimum_withdrawal,
    callback_mode,
    web_max_file_size_mb,
    web_upload_rate_limit,
    web_upload_rate_window,
    api_rate_limit,
    api_rate_window,
    maintenance_mode,
    subscriptions_enabled,
    created_at,
    updated_at
)
SELECT
    1,
    0.0,  -- Default impression rate
    0.0,  -- Default cutback percentage
    10.0,  -- Default minimum withdrawal
    'POST',  -- Default callback mode
    2048,  -- Default max file size (2GB)
    10,  -- Default web upload rate limit
    3600,  -- Default web upload rate window (1 hour)
    100,  -- Default API rate limit
    3600,  -- Default API rate window (1 hour)
    false,  -- Maintenance mode off
    false,  -- Subscriptions disabled
    NOW(),
    NOW()
WHERE NOT EXISTS (SELECT 1 FROM settings LIMIT 1);
