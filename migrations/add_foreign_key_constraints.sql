-- Migration: Add Foreign Key Constraints
-- Date: November 12, 2025
-- Description: Add proper foreign key relationships to enforce referential integrity
-- WARNING: This migration should be run after cleaning up any orphaned records

-- Files table foreign keys
ALTER TABLE files 
    ADD CONSTRAINT fk_files_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE SET NULL;

-- AccessLog table foreign keys
ALTER TABLE access_logs 
    ADD CONSTRAINT fk_access_logs_file 
    FOREIGN KEY (file_id) 
    REFERENCES files(id) 
    ON DELETE CASCADE;

-- DeviceLink table foreign keys
ALTER TABLE device_links 
    ADD CONSTRAINT fk_device_links_file 
    FOREIGN KEY (file_id) 
    REFERENCES files(id) 
    ON DELETE CASCADE;

-- LinkTransaction table foreign keys
ALTER TABLE link_transactions 
    ADD CONSTRAINT fk_link_transactions_file 
    FOREIGN KEY (file_id) 
    REFERENCES files(id) 
    ON DELETE CASCADE;

-- PublisherImpression table foreign keys
ALTER TABLE publisher_impressions 
    ADD CONSTRAINT fk_publisher_impressions_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

-- BankAccount table foreign keys
ALTER TABLE bank_accounts 
    ADD CONSTRAINT fk_bank_accounts_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

-- WithdrawalRequest table foreign keys
ALTER TABLE withdrawal_requests 
    ADD CONSTRAINT fk_withdrawal_requests_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

ALTER TABLE withdrawal_requests 
    ADD CONSTRAINT fk_withdrawal_requests_bank_account 
    FOREIGN KEY (bank_account_id) 
    REFERENCES bank_accounts(id) 
    ON DELETE RESTRICT;

-- Ticket table foreign keys
ALTER TABLE tickets 
    ADD CONSTRAINT fk_tickets_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

-- ImpressionAdjustment table foreign keys
ALTER TABLE impression_adjustments 
    ADD CONSTRAINT fk_impression_adjustments_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

-- PublisherRegistration table foreign keys
ALTER TABLE publisher_registrations 
    ADD CONSTRAINT fk_publisher_registrations_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

-- PublisherLoginEvent table foreign keys (nullable)
ALTER TABLE publisher_login_events 
    ADD CONSTRAINT fk_publisher_login_events_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE SET NULL;

-- PublisherAccountLink table foreign keys
ALTER TABLE publisher_account_links 
    ADD CONSTRAINT fk_publisher_account_links_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

ALTER TABLE publisher_account_links 
    ADD CONSTRAINT fk_publisher_account_links_related_publisher 
    FOREIGN KEY (related_publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

-- AdPlayCount table foreign keys
ALTER TABLE ad_play_counts 
    ADD CONSTRAINT fk_ad_play_counts_ad_network 
    FOREIGN KEY (ad_network_id) 
    REFERENCES ad_networks(id) 
    ON DELETE CASCADE;

-- AdPlayTracking table foreign keys
ALTER TABLE ad_play_tracking 
    ADD CONSTRAINT fk_ad_play_tracking_ad_network 
    FOREIGN KEY (ad_network_id) 
    REFERENCES ad_networks(id) 
    ON DELETE CASCADE;

-- ReferralCode table foreign keys
ALTER TABLE referral_codes 
    ADD CONSTRAINT fk_referral_codes_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

-- Referral table foreign keys
ALTER TABLE referrals 
    ADD CONSTRAINT fk_referrals_referrer 
    FOREIGN KEY (referrer_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

ALTER TABLE referrals 
    ADD CONSTRAINT fk_referrals_referred_publisher 
    FOREIGN KEY (referred_publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

-- ReferralReward table foreign keys
ALTER TABLE referral_rewards 
    ADD CONSTRAINT fk_referral_rewards_referral 
    FOREIGN KEY (referral_id) 
    REFERENCES referrals(id) 
    ON DELETE CASCADE;

ALTER TABLE referral_rewards 
    ADD CONSTRAINT fk_referral_rewards_referrer 
    FOREIGN KEY (referrer_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

ALTER TABLE referral_rewards 
    ADD CONSTRAINT fk_referral_rewards_referred_publisher 
    FOREIGN KEY (referred_publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

ALTER TABLE referral_rewards 
    ADD CONSTRAINT fk_referral_rewards_withdrawal 
    FOREIGN KEY (withdrawal_id) 
    REFERENCES withdrawal_requests(id) 
    ON DELETE SET NULL;

-- Subscription table foreign keys
ALTER TABLE subscriptions 
    ADD CONSTRAINT fk_subscriptions_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE SET NULL;

ALTER TABLE subscriptions 
    ADD CONSTRAINT fk_subscriptions_plan 
    FOREIGN KEY (plan_id) 
    REFERENCES subscription_plans(id) 
    ON DELETE SET NULL;

-- PremiumLinkEarning table foreign keys
ALTER TABLE premium_link_earnings 
    ADD CONSTRAINT fk_premium_link_earnings_publisher 
    FOREIGN KEY (publisher_id) 
    REFERENCES publishers(id) 
    ON DELETE CASCADE;

ALTER TABLE premium_link_earnings 
    ADD CONSTRAINT fk_premium_link_earnings_plan 
    FOREIGN KEY (plan_id) 
    REFERENCES subscription_plans(id) 
    ON DELETE CASCADE;

ALTER TABLE premium_link_earnings 
    ADD CONSTRAINT fk_premium_link_earnings_subscription 
    FOREIGN KEY (subscription_id) 
    REFERENCES subscriptions(id) 
    ON DELETE CASCADE;

-- Add index for improved query performance on foreign keys
CREATE INDEX IF NOT EXISTS idx_rate_limits_key_request_time ON rate_limits(key, request_time);
