-- Migration: Add Composite Index for Impression Deduplication
-- Date: November 12, 2025
-- Description: Adds composite index to improve performance of duplicate impression detection
-- Related to BUG #13: No Limit on Impressions Per User

-- Add composite index for faster duplicate detection
CREATE INDEX IF NOT EXISTS idx_publisher_impressions_android_hash_date 
    ON publisher_impressions(android_id, hash_id, impression_date);

-- Add index for impression cleanup queries
CREATE INDEX IF NOT EXISTS idx_publisher_impressions_created_at 
    ON publisher_impressions(created_at);
