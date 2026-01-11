-- Add Paytm payment gateway configuration fields to settings table
-- This migration adds fields for storing Paytm credentials in the admin panel

ALTER TABLE settings ADD COLUMN IF NOT EXISTS paytm_mid VARCHAR(255);
ALTER TABLE settings ADD COLUMN IF NOT EXISTS paytm_upi_id VARCHAR(255);
ALTER TABLE settings ADD COLUMN IF NOT EXISTS paytm_unit_id VARCHAR(255);
ALTER TABLE settings ADD COLUMN IF NOT EXISTS paytm_signature TEXT;

-- Add comments for documentation
COMMENT ON COLUMN settings.paytm_mid IS 'Paytm Merchant ID for payment processing';
COMMENT ON COLUMN settings.paytm_upi_id IS 'UPI ID for receiving payments';
COMMENT ON COLUMN settings.paytm_unit_id IS 'Business/Payee name shown to customers';
COMMENT ON COLUMN settings.paytm_signature IS 'Paytm signature for app intent (optional)';
