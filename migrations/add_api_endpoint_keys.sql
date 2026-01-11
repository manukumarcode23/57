-- Migration: Add API Endpoint Keys table for managing API keys per endpoint
-- Date: 2025-11-04

CREATE TABLE IF NOT EXISTS api_endpoint_keys (
    id SERIAL PRIMARY KEY,
    endpoint_name VARCHAR(255) UNIQUE NOT NULL,
    endpoint_path VARCHAR(500) NOT NULL,
    api_key VARCHAR(128) UNIQUE NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_api_endpoint_keys_endpoint_name ON api_endpoint_keys(endpoint_name);
CREATE INDEX IF NOT EXISTS idx_api_endpoint_keys_api_key ON api_endpoint_keys(api_key);

-- Insert default API endpoints
INSERT INTO api_endpoint_keys (endpoint_name, endpoint_path, api_key, description, is_active) VALUES
    ('API Request', '/api/request', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'File access request endpoint', true),
    ('API Postback', '/api/postback', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Link generation with callback support', true),
    ('API Links', '/api/links', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Retrieve generated links endpoint', true),
    ('API Tracking Postback', '/api/tracking/postback', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Video impression tracking endpoint', true),
    ('Ads API - Banner', '/api/banner_ads', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Banner ad networks endpoint', true),
    ('Ads API - Interstitial', '/api/interstitial_ads', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Interstitial ad networks endpoint', true),
    ('Ads API - Rewarded', '/api/rewarded_ads', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Rewarded ad networks endpoint', true),
    ('Ads API - All Ads', '/api/all_ads', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'All ad networks endpoint', true),
    ('Ads API - Record Play', '/api/record_ad_play', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Record ad play endpoint', true),
    ('Ads API - Ad Limits', '/api/ad_limits', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Ad limit tracking endpoint', true)
ON CONFLICT (endpoint_name) DO NOTHING;
