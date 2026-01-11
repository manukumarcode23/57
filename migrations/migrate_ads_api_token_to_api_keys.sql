-- Migration: Move ads_api_token from Settings to API Keys
-- Date: 2025-11-04
-- Description: Migrates the ads_api_token from the settings table to the api_endpoint_keys table

-- Step 1: Migrate existing ads_api_token from settings to api_endpoint_keys ONLY if it exists
-- If no DB token exists, the system will continue to use AD_API_TOKEN environment variable fallback
DO $$
DECLARE
    existing_token TEXT;
BEGIN
    -- Get the current ads_api_token from settings if it exists
    SELECT ads_api_token INTO existing_token FROM settings WHERE ads_api_token IS NOT NULL AND ads_api_token != '' LIMIT 1;
    
    -- Only create API key entry if there was an actual token in the database
    IF existing_token IS NOT NULL THEN
        INSERT INTO api_endpoint_keys (endpoint_name, endpoint_path, api_key, description, is_active)
        VALUES (
            'Ads API',
            '/api/ads',
            existing_token,
            'Unified API token for all ad network endpoints (banner_ads, interstitial_ads, rewarded_ads, all_ads, record_ad_play, ad_limits)',
            true
        )
        ON CONFLICT (endpoint_name) DO UPDATE
        SET api_key = EXCLUDED.api_key,
            description = EXCLUDED.description,
            is_active = true,
            updated_at = CURRENT_TIMESTAMP;
        
        RAISE NOTICE 'Migrated ads_api_token from settings to API Keys table as "Ads API"';
    ELSE
        RAISE NOTICE 'No ads_api_token found in settings - system will use AD_API_TOKEN environment variable fallback or admin can configure via API Keys page';
    END IF;
END $$;

-- Step 2: Remove the old separate ads API endpoint entries if they exist (from old migration)
DELETE FROM api_endpoint_keys 
WHERE endpoint_name IN (
    'Ads API - Banner',
    'Ads API - Interstitial', 
    'Ads API - Rewarded',
    'Ads API - All Ads',
    'Ads API - Record Play',
    'Ads API - Ad Limits'
);

-- Step 3: Remove the ads_api_token column from settings table
-- Note: This is a destructive operation and should be done after confirming the migration
ALTER TABLE settings DROP COLUMN IF EXISTS ads_api_token;

-- Verification
SELECT 
    CASE 
        WHEN EXISTS (SELECT 1 FROM api_endpoint_keys WHERE endpoint_name = 'Ads API') 
        THEN 'SUCCESS: Ads API token migrated to API Keys'
        ELSE 'WARNING: Ads API token migration may have failed'
    END as migration_status;
