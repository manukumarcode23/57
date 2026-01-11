-- Migration: Add subscriptions table for payment tracking
-- Date: 2025-11-07
-- Description: Creates subscriptions table to track Paytm payment subscriptions

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    publisher_id INTEGER NOT NULL,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    plan_name VARCHAR(100) NOT NULL,
    amount FLOAT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' NOT NULL,
    payment_method VARCHAR(50) DEFAULT 'paytm' NOT NULL,
    utr_number VARCHAR(100),
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    paid_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_subscription_publisher ON subscriptions(publisher_id, status);
CREATE INDEX IF NOT EXISTS idx_subscription_order ON subscriptions(order_id);

-- Add trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_subscriptions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_subscriptions_updated_at ON subscriptions;
CREATE TRIGGER trigger_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_subscriptions_updated_at();
