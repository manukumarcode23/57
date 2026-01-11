-- Migration: Add subscription management features
-- This adds the subscription toggle and subscription plans table

-- Add subscriptions_enabled flag to settings table
ALTER TABLE settings ADD COLUMN IF NOT EXISTS subscriptions_enabled BOOLEAN DEFAULT FALSE;

-- Create subscription_plans table for admin-managed plans
CREATE TABLE IF NOT EXISTS subscription_plans (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    amount FLOAT NOT NULL,
    duration_days INTEGER NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Add new columns to subscriptions table
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_id INTEGER REFERENCES subscription_plans(id);
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS duration_days INTEGER DEFAULT 30;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_subscription_plans_active ON subscription_plans(is_active);
CREATE INDEX IF NOT EXISTS idx_subscription_plan_id ON subscriptions(plan_id);

-- Insert default subscription plans
INSERT INTO subscription_plans (name, amount, duration_days, description, is_active) 
VALUES 
    ('Basic Plan', 99, 30, 'Basic monthly subscription', TRUE),
    ('Premium Plan - 6 Months', 499, 180, '6 months subscription with premium features', TRUE),
    ('Yearly Plan', 999, 365, 'Annual subscription - Best value', TRUE)
ON CONFLICT DO NOTHING;

-- Update timestamp trigger for subscription_plans
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_subscription_plans_updated_at ON subscription_plans;
CREATE TRIGGER update_subscription_plans_updated_at 
    BEFORE UPDATE ON subscription_plans 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
