-- Migration: Add Web Publisher Subscription Tables
-- Purpose: Create tables for web publisher video upload subscriptions (separate from Android app subscriptions)

-- Create web publisher subscription plans table
CREATE TABLE IF NOT EXISTS web_publisher_subscription_plans (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    amount FLOAT NOT NULL,
    duration_days INTEGER NOT NULL,
    upload_limit INTEGER DEFAULT 0,
    max_file_size_mb INTEGER DEFAULT 2048,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for active plans
CREATE INDEX IF NOT EXISTS idx_web_plan_active ON web_publisher_subscription_plans(is_active);

-- Create web publisher subscriptions table
CREATE TABLE IF NOT EXISTS web_publisher_subscriptions (
    id SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL REFERENCES publishers(id) ON DELETE CASCADE,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    plan_id INTEGER REFERENCES web_publisher_subscription_plans(id) ON DELETE SET NULL,
    plan_name VARCHAR(100) NOT NULL,
    amount FLOAT NOT NULL,
    duration_days INTEGER DEFAULT 30,
    upload_limit INTEGER DEFAULT 0,
    max_file_size_mb INTEGER DEFAULT 2048,
    uploads_used INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    payment_method VARCHAR(50) DEFAULT 'paytm',
    utr_number VARCHAR(100),
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    paid_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_web_sub_publisher ON web_publisher_subscriptions(publisher_id, status);
CREATE INDEX IF NOT EXISTS idx_web_sub_order ON web_publisher_subscriptions(order_id);
CREATE INDEX IF NOT EXISTS idx_web_sub_expires ON web_publisher_subscriptions(publisher_id, expires_at);

-- Add web_publisher_subscriptions_enabled to settings if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'settings' AND column_name = 'web_publisher_subscriptions_enabled'
    ) THEN
        ALTER TABLE settings ADD COLUMN web_publisher_subscriptions_enabled BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Insert a sample plan (optional - can be removed or modified)
-- INSERT INTO web_publisher_subscription_plans (name, amount, duration_days, upload_limit, max_file_size_mb, description)
-- VALUES ('Basic Web Upload Plan', 199.0, 30, 100, 2048, 'Upload up to 100 videos per month with 2GB max file size');
