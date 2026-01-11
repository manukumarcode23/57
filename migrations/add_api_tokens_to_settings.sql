-- Migration to add API token fields to settings table
-- This allows admins to configure API tokens directly in the admin panel

ALTER TABLE settings ADD COLUMN IF NOT EXISTS global_api_token VARCHAR(128);
ALTER TABLE settings ADD COLUMN IF NOT EXISTS ads_api_token VARCHAR(128);
ALTER TABLE settings ADD COLUMN IF NOT EXISTS payment_api_token VARCHAR(128);
