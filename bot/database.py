from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from os import environ
from logging import getLogger
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv
from pathlib import Path
from secrets import token_hex
import asyncio

# Load .env file to ensure DATABASE_URL is available (do not override Replit-provided vars)
load_dotenv(Path(__file__).parent.parent / '.env', override=False)

logger = getLogger('bot.database')

class Base(DeclarativeBase):
    pass

# Create async engine
database_url = environ.get("DATABASE_URL") or "postgresql://neondb_owner:npg_mNDbtZQOGd95@ep-dark-credit-adli956l-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
if not database_url:
    raise ValueError("DATABASE_URL environment variable is required")

# Parse the URL and remove SSL-related parameters that asyncpg doesn't support
parsed_url = urlparse(database_url)
# Remove query parameters like sslmode
clean_url = urlunparse((
    parsed_url.scheme,
    parsed_url.netloc,
    parsed_url.path,
    parsed_url.params,
    '',  # Remove query string
    parsed_url.fragment
))

DB_POOL_SIZE = int(environ.get("DB_POOL_SIZE") or "10")
DB_MAX_OVERFLOW = int(environ.get("DB_MAX_OVERFLOW") or "20")
DB_POOL_RECYCLE = int(environ.get("DB_POOL_RECYCLE") or "300")

engine = create_async_engine(
    clean_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False,  # Set to True for SQL query logging
    pool_pre_ping=True,
    pool_recycle=DB_POOL_RECYCLE,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    connect_args={
        "server_settings": {
            "application_name": "telegram_bot",
        }
    }
)

# Create async session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def generate_unique_access_code(max_retries=5) -> str:
    """
    Generate unique access code with retry logic to prevent collisions.
    Retries up to max_retries times if collision detected.
    """
    from bot.models import File
    from sqlalchemy import select
    from bot.config import Telegram
    
    import string
    import random
    
    # Use letters (uppercase + lowercase) and digits for a readable alphanumeric code
    # Excluding confusing characters like 0, O, I, l
    chars = string.ascii_letters + string.digits
    chars = chars.translate(str.maketrans('', '', '0OIl'))
    
    for attempt in range(max_retries):
        access_code = ''.join(random.choices(chars, k=Telegram.SECRET_CODE_LENGTH))
        
        # Check if code already exists in database
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(File).where(File.access_code == access_code)
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                return access_code
        
        # If collision detected, wait briefly and retry
        if attempt < max_retries - 1:
            await asyncio.sleep(0.1)
            logger.warning(f"Access code collision detected, retrying... (attempt {attempt + 1}/{max_retries})")
    
    # If all retries fail, raise an error
    raise RuntimeError("Failed to generate unique access code after maximum retries")

async def create_default_admin():
    """Create or update default admin account with current password"""
    from bot.models import Publisher
    import bcrypt
    
    # Admin account configuration with default password
    default_admin_email = (environ.get("ADMIN_EMAIL") or "admin@bot.com").lower().strip()
    default_admin_password = environ.get("ADMIN_PASSWORD") or "Admin@123"
    
    async with AsyncSessionLocal() as session:
        try:
            from sqlalchemy import select, func
            
            result = await session.execute(
                select(Publisher).where(func.lower(Publisher.email) == default_admin_email)
            )
            existing_admin = result.scalar_one_or_none()
            
            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(default_admin_password.encode('utf-8'), salt).decode('utf-8')
            
            if not existing_admin:
                admin = Publisher(
                    email=default_admin_email,
                    password_hash=password_hash,
                    traffic_source="System Admin",
                    is_admin=True,
                    is_active=True
                )
                
                session.add(admin)
                await session.commit()
                logger.info(f"Default admin account created: {default_admin_email}")
            else:
                existing_admin.password_hash = password_hash
                existing_admin.is_admin = True
                existing_admin.is_active = True
                await session.commit()
                logger.info(f"Admin account password updated: {default_admin_email}")
                
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating/updating default admin: {e}")

async def create_default_api_keys():
    """Create default API keys for Ads API endpoints"""
    from bot.models import ApiEndpointKey
    from sqlalchemy import select
    
    default_api_keys = [
        {
            'endpoint_name': 'Banner Ads API',
            'endpoint_path': '/api/banner_ads',
            'description': 'API key for banner ads endpoint - Get all banner ad networks with daily limits',
            'api_key': environ.get('AD_API_TOKEN') or token_hex(32)
        },
        {
            'endpoint_name': 'Interstitial Ads API',
            'endpoint_path': '/api/interstitial_ads',
            'description': 'API key for interstitial ads endpoint - Get all interstitial ad networks with daily limits',
            'api_key': environ.get('AD_API_TOKEN') or token_hex(32)
        },
        {
            'endpoint_name': 'Rewarded Ads API',
            'endpoint_path': '/api/rewarded_ads',
            'description': 'API key for rewarded ads endpoint - Get all rewarded ad networks with daily limits',
            'api_key': environ.get('AD_API_TOKEN') or token_hex(32)
        },
        {
            'endpoint_name': 'All Ads API',
            'endpoint_path': '/api/all_ads',
            'description': 'API key for all ads endpoint - Get complete ad network configuration for all ad types',
            'api_key': environ.get('AD_API_TOKEN') or token_hex(32)
        }
    ]
    
    async with AsyncSessionLocal() as session:
        try:
            for key_config in default_api_keys:
                result = await session.execute(
                    select(ApiEndpointKey).where(
                        ApiEndpointKey.endpoint_path == key_config['endpoint_path']
                    )
                )
                existing_key = result.scalar_one_or_none()
                
                if not existing_key:
                    api_key = ApiEndpointKey(
                        endpoint_name=key_config['endpoint_name'],
                        endpoint_path=key_config['endpoint_path'],
                        api_key=key_config['api_key'],
                        description=key_config['description'],
                        is_active=True
                    )
                    session.add(api_key)
                    logger.info(f"Default API key created: {key_config['endpoint_name']}")
            
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating default API keys: {e}")

async def create_default_settings():
    """Create default settings record if it doesn't exist"""
    from bot.models import Settings
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(Settings))
            existing_settings = result.scalar_one_or_none()
            
            if not existing_settings:
                settings = Settings()
                session.add(settings)
                await session.commit()
                logger.info("Default settings record created")
            else:
                logger.info("Settings record already exists")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error creating default settings: {e}")

async def run_migrations():
    """Run database migrations for schema changes"""
    from sqlalchemy import text
    
    async with engine.begin() as conn:
        try:
            # Add android_package_name column if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS android_package_name VARCHAR(255)"
            ))
            # Add android_deep_link_scheme column if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS android_deep_link_scheme VARCHAR(100)"
            ))
            # Add minimum_withdrawal column if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS minimum_withdrawal FLOAT DEFAULT 10.0"
            ))
            # Update NULL minimum_withdrawal values to default
            await conn.execute(text(
                "UPDATE settings SET minimum_withdrawal = 10.0 WHERE minimum_withdrawal IS NULL"
            ))
            # Add balance column to publishers table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE publishers ADD COLUMN IF NOT EXISTS balance FLOAT DEFAULT 0.0"
            ))
            # Add last_login_ip column to publishers table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE publishers ADD COLUMN IF NOT EXISTS last_login_ip VARCHAR(45)"
            ))
            # Add last_login_geo column to publishers table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE publishers ADD COLUMN IF NOT EXISTS last_login_geo VARCHAR(100)"
            ))
            # Add custom_impression_rate column to publishers table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE publishers ADD COLUMN IF NOT EXISTS custom_impression_rate FLOAT"
            ))
            # Add CHECK constraint for custom_impression_rate to ensure non-negative values
            await conn.execute(text(
                "ALTER TABLE publishers DROP CONSTRAINT IF EXISTS check_custom_rate_non_negative"
            ))
            await conn.execute(text(
                "ALTER TABLE publishers ADD CONSTRAINT check_custom_rate_non_negative CHECK (custom_impression_rate IS NULL OR custom_impression_rate >= 0)"
            ))
            # Add thumbnail_path column to publishers table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE publishers ADD COLUMN IF NOT EXISTS thumbnail_path VARCHAR(500)"
            ))
            # Add thumbnail_approved column to publishers table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE publishers ADD COLUMN IF NOT EXISTS thumbnail_approved BOOLEAN DEFAULT FALSE NOT NULL"
            ))
            # Add logo_path column to publishers table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE publishers ADD COLUMN IF NOT EXISTS logo_path VARCHAR(255)"
            ))
            # Add default_video_description column to publishers table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE publishers ADD COLUMN IF NOT EXISTS default_video_description TEXT"
            ))
            # Update existing publishers to have thumbnail_approved=false for those with thumbnails
            await conn.execute(text(
                "UPDATE publishers SET thumbnail_approved = FALSE WHERE thumbnail_path IS NOT NULL AND thumbnail_approved IS NULL"
            ))
            # Add index for faster queries on thumbnail approval status
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_publishers_thumbnail_approved ON publishers(thumbnail_approved) WHERE thumbnail_path IS NOT NULL"
            ))
            # Add default_thumbnail_path column to settings table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS default_thumbnail_path VARCHAR(255)"
            ))
            # Add ads_api_token column to settings if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS ads_api_token TEXT"
            ))
            # Add callback_mode column to settings if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS callback_mode VARCHAR(10) DEFAULT 'POST'"
            ))
            # Add callback_method column to link_transactions if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE link_transactions ADD COLUMN IF NOT EXISTS callback_method VARCHAR(10)"
            ))
            
            # Add thumbnail_file_id column to files table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE files ADD COLUMN IF NOT EXISTS thumbnail_file_id VARCHAR(255)"
            ))
            # Add custom_description column to files table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE files ADD COLUMN IF NOT EXISTS custom_description TEXT"
            ))
            # Add r2_object_key column to files table if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE files ADD COLUMN IF NOT EXISTS r2_object_key VARCHAR(255)"
            ))
            
            # Add new limit configuration columns to settings table
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS web_max_file_size_mb INTEGER DEFAULT 2048"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS web_upload_rate_limit INTEGER DEFAULT 10"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS web_upload_rate_window INTEGER DEFAULT 3600"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS api_rate_limit INTEGER DEFAULT 100"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS api_rate_window INTEGER DEFAULT 3600"
            ))
            
            # Add impression_cutback_percentage column to settings if it doesn't exist
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS impression_cutback_percentage FLOAT DEFAULT 0.0"
            ))
            
            # Create bank_accounts table if it doesn't exist
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS bank_accounts (
                    id SERIAL PRIMARY KEY,
                    publisher_id INTEGER NOT NULL,
                    account_holder_name VARCHAR(255) NOT NULL,
                    bank_name VARCHAR(255) NOT NULL,
                    account_number VARCHAR(100) NOT NULL,
                    routing_number VARCHAR(50),
                    swift_code VARCHAR(50),
                    country VARCHAR(100) NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create withdrawal_requests table if it doesn't exist
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    id SERIAL PRIMARY KEY,
                    publisher_id INTEGER NOT NULL,
                    bank_account_id INTEGER NOT NULL,
                    amount FLOAT NOT NULL,
                    status VARCHAR(20) DEFAULT 'pending',
                    admin_note TEXT,
                    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP WITH TIME ZONE
                )
            """))
            
            # Create indexes for better query performance
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_bank_accounts_publisher_id ON bank_accounts(publisher_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_publisher_id ON withdrawal_requests(publisher_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_withdrawal_requests_bank_account_id ON withdrawal_requests(bank_account_id)"
            ))
            
            # Add country and region fields to publisher_impressions table
            await conn.execute(text(
                "ALTER TABLE publisher_impressions ADD COLUMN IF NOT EXISTS country_code VARCHAR(2)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_impressions ADD COLUMN IF NOT EXISTS country_name VARCHAR(100)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_impressions ADD COLUMN IF NOT EXISTS region VARCHAR(100)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_publisher_impressions_country_code ON publisher_impressions(country_code)"
            ))
            
            # Create country_rates table if it doesn't exist
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS country_rates (
                    id SERIAL PRIMARY KEY,
                    country_code VARCHAR(2) UNIQUE NOT NULL,
                    country_name VARCHAR(100) NOT NULL,
                    impression_rate FLOAT DEFAULT 0.0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_country_rates_country_code ON country_rates(country_code)"
            ))
            
            # Backup and log duplicate data before deletion
            try:
                # First, create a backup table for duplicate publishers
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS publishers_duplicates_backup (
                        id INT, email VARCHAR(255), password_hash VARCHAR(255),
                        balance FLOAT, traffic_source VARCHAR(255), is_active BOOLEAN,
                        is_admin BOOLEAN, api_key VARCHAR(64), telegram_id BIGINT,
                        created_at TIMESTAMP, deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (id)
                    )
                """))
                
                # Log duplicate publishers before deleting
                result = await conn.execute(text("""
                    SELECT a.id, a.email, a.balance, a.created_at
                    FROM publishers a
                    INNER JOIN publishers b ON LOWER(a.email) = LOWER(b.email) AND a.id > b.id
                """))
                duplicates = result.fetchall()
                
                if duplicates:
                    logger.warning(f"Found {len(duplicates)} duplicate publisher(s) to be removed:")
                    for dup in duplicates:
                        logger.warning(f"  - ID: {dup[0]}, Email: {dup[1]}, Balance: ${dup[2]:.2f}, Created: {dup[3]}")
                    
                    # Backup duplicates before deletion
                    await conn.execute(text("""
                        INSERT INTO publishers_duplicates_backup 
                        (id, email, password_hash, balance, traffic_source, is_active, is_admin, api_key, telegram_id, created_at)
                        SELECT a.id, a.email, a.password_hash, a.balance, a.traffic_source, a.is_active, a.is_admin, a.api_key, a.telegram_id, a.created_at
                        FROM publishers a
                        INNER JOIN publishers b ON LOWER(a.email) = LOWER(b.email) AND a.id > b.id
                    """))
                    logger.info(f"Backed up {len(duplicates)} duplicate publisher(s) to publishers_duplicates_backup table")
                
                # Now delete duplicates
                await conn.execute(text("""
                    DELETE FROM publishers a USING publishers b
                    WHERE a.id > b.id
                    AND LOWER(a.email) = LOWER(b.email)
                """))
                logger.info("Removed duplicate email addresses (case-insensitive)")
            except Exception as e:
                logger.error(f"Error handling duplicate emails: {e}")
                # Don't fail the migration, just log the error
                pass
            
            await conn.execute(text(
                "UPDATE publishers SET email = LOWER(email) WHERE email != LOWER(email)"
            ))
            logger.info("Normalized all email addresses to lowercase")
            
            try:
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_publishers_email_lower ON publishers (LOWER(email))"
                ))
                logger.info("Created unique index on lowercase email")
            except Exception as e:
                logger.warning(f"Could not create unique email index: {e}")
            
            # Add welcome bonus columns to referral_settings table if they don't exist
            await conn.execute(text(
                "ALTER TABLE referral_settings ADD COLUMN IF NOT EXISTS new_publisher_welcome_bonus_enabled BOOLEAN DEFAULT FALSE"
            ))
            await conn.execute(text(
                "ALTER TABLE referral_settings ADD COLUMN IF NOT EXISTS new_publisher_welcome_bonus_amount FLOAT DEFAULT 0.0"
            ))
            
            # Add logo and favicon paths to settings table
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS logo_path VARCHAR(255)"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS favicon_path VARCHAR(255)"
            ))
            
            # Add maintenance_mode column to settings table
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS maintenance_mode BOOLEAN DEFAULT FALSE"
            ))
            
            # Create api_endpoint_keys table for managing API keys per endpoint
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS api_endpoint_keys (
                    id SERIAL PRIMARY KEY,
                    endpoint_name VARCHAR(255) UNIQUE NOT NULL,
                    endpoint_path VARCHAR(500) NOT NULL,
                    api_key VARCHAR(128) UNIQUE NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_api_endpoint_keys_endpoint_name ON api_endpoint_keys(endpoint_name)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_api_endpoint_keys_api_key ON api_endpoint_keys(api_key)"
            ))
            
            # Insert default API endpoints if they don't exist
            await conn.execute(text("""
                INSERT INTO api_endpoint_keys (endpoint_name, endpoint_path, api_key, description, is_active)
                SELECT 'API Request', '/api/request', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'File access request endpoint', true
                WHERE NOT EXISTS (SELECT 1 FROM api_endpoint_keys WHERE endpoint_name = 'API Request')
            """))
            await conn.execute(text("""
                INSERT INTO api_endpoint_keys (endpoint_name, endpoint_path, api_key, description, is_active)
                SELECT 'API Postback', '/api/postback', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Link generation with callback support', true
                WHERE NOT EXISTS (SELECT 1 FROM api_endpoint_keys WHERE endpoint_name = 'API Postback')
            """))
            await conn.execute(text("""
                INSERT INTO api_endpoint_keys (endpoint_name, endpoint_path, api_key, description, is_active)
                SELECT 'API Links', '/api/links', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Retrieve generated links endpoint', true
                WHERE NOT EXISTS (SELECT 1 FROM api_endpoint_keys WHERE endpoint_name = 'API Links')
            """))
            await conn.execute(text("""
                INSERT INTO api_endpoint_keys (endpoint_name, endpoint_path, api_key, description, is_active)
                SELECT 'API Tracking Postback', '/api/tracking/postback', 'default_' || md5(random()::text || clock_timestamp()::text)::text, 'Video impression tracking endpoint', true
                WHERE NOT EXISTS (SELECT 1 FROM api_endpoint_keys WHERE endpoint_name = 'API Tracking Postback')
            """))
            
            # Add device fingerprint and detection fields to publisher_registrations table
            await conn.execute(text(
                "ALTER TABLE publisher_registrations ADD COLUMN IF NOT EXISTS device_fingerprint VARCHAR(64)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_registrations ADD COLUMN IF NOT EXISTS hardware_fingerprint VARCHAR(64)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_registrations ADD COLUMN IF NOT EXISTS device_type VARCHAR(50)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_registrations ADD COLUMN IF NOT EXISTS device_name VARCHAR(100)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_registrations ADD COLUMN IF NOT EXISTS operating_system VARCHAR(100)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_registrations ADD COLUMN IF NOT EXISTS browser_name VARCHAR(50)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_registrations ADD COLUMN IF NOT EXISTS browser_version VARCHAR(50)"
            ))
            
            # Add device fingerprint and detection fields to publisher_login_events table
            await conn.execute(text(
                "ALTER TABLE publisher_login_events ADD COLUMN IF NOT EXISTS device_fingerprint VARCHAR(64)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_login_events ADD COLUMN IF NOT EXISTS device_type VARCHAR(50)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_login_events ADD COLUMN IF NOT EXISTS device_name VARCHAR(100)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_login_events ADD COLUMN IF NOT EXISTS operating_system VARCHAR(100)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_login_events ADD COLUMN IF NOT EXISTS browser_name VARCHAR(50)"
            ))
            await conn.execute(text(
                "ALTER TABLE publisher_login_events ADD COLUMN IF NOT EXISTS browser_version VARCHAR(50)"
            ))
            
            # Create indexes for efficient device fingerprint querying
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_registration_fingerprint ON publisher_registrations(device_fingerprint, created_at)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_registration_hardware_fingerprint ON publisher_registrations(hardware_fingerprint)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_login_fingerprint ON publisher_login_events(device_fingerprint, created_at)"
            ))
            
            # Add subscriptions_enabled flag to settings table
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS subscriptions_enabled BOOLEAN DEFAULT FALSE"
            ))
            
            # Create subscription_plans table for admin-managed plans
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS subscription_plans (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    amount FLOAT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Add new columns to subscriptions table
            await conn.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS plan_id INTEGER"
            ))
            await conn.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS duration_days INTEGER DEFAULT 30"
            ))
            await conn.execute(text(
                "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS android_id VARCHAR(255)"
            ))
            # Make publisher_id nullable for android subscriptions
            await conn.execute(text(
                "ALTER TABLE subscriptions ALTER COLUMN publisher_id DROP NOT NULL"
            ))
            
            # Create indexes for performance
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_subscription_plans_active ON subscription_plans(is_active)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_subscription_plan_id ON subscriptions(plan_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_subscription_android ON subscriptions(android_id, status)"
            ))
            
            # Insert default subscription plans if they don't exist
            await conn.execute(text("""
                INSERT INTO subscription_plans (name, amount, duration_days, description, is_active) 
                SELECT 'Basic Plan', 99, 30, 'Basic monthly subscription', TRUE
                WHERE NOT EXISTS (SELECT 1 FROM subscription_plans WHERE name = 'Basic Plan')
            """))
            await conn.execute(text("""
                INSERT INTO subscription_plans (name, amount, duration_days, description, is_active) 
                SELECT 'Premium Plan - 6 Months', 499, 180, '6 months subscription with premium features', TRUE
                WHERE NOT EXISTS (SELECT 1 FROM subscription_plans WHERE name = 'Premium Plan - 6 Months')
            """))
            await conn.execute(text("""
                INSERT INTO subscription_plans (name, amount, duration_days, description, is_active) 
                SELECT 'Yearly Plan', 999, 365, 'Annual subscription - Best value', TRUE
                WHERE NOT EXISTS (SELECT 1 FROM subscription_plans WHERE name = 'Yearly Plan')
            """))
            
            # Add Paytm payment gateway configuration fields to settings table
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS paytm_mid VARCHAR(255)"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS paytm_upi_id VARCHAR(255)"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS paytm_unit_id VARCHAR(255)"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS paytm_signature TEXT"
            ))
            
            # Add centralized API token management columns to settings
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS global_api_token VARCHAR(128)"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS payment_api_token VARCHAR(128)"
            ))
            # Note: ads_api_token already exists as TEXT, let's update it to be consistent
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS ads_api_token VARCHAR(128)"
            ))
            
            # Add web_publisher_subscriptions_enabled flag to settings table
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS web_publisher_subscriptions_enabled BOOLEAN DEFAULT FALSE"
            ))
            
            # Create web_publisher_subscription_plans table for web upload subscriptions
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS web_publisher_subscription_plans (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    amount FLOAT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    upload_limit INTEGER DEFAULT 0,
                    max_file_size_mb INTEGER DEFAULT 2048,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_web_plan_active ON web_publisher_subscription_plans(is_active)"
            ))
            
            # Create web_publisher_subscriptions table for tracking web upload subscriptions
            await conn.execute(text("""
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
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    paid_at TIMESTAMP WITH TIME ZONE
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_web_sub_publisher ON web_publisher_subscriptions(publisher_id, status)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_web_sub_order ON web_publisher_subscriptions(order_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_web_sub_expires ON web_publisher_subscriptions(publisher_id, expires_at)"
            ))
            
            # Add IPQS (IP Quality Score) integration columns to settings table
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS ipqs_api_key VARCHAR(255)"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS ipqs_secret_key VARCHAR(255)"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS ipqs_enabled BOOLEAN DEFAULT FALSE"
            ))
            
            # Add R2 storage configuration columns to settings table
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS r2_storage_enabled BOOLEAN DEFAULT FALSE"
            ))
            await conn.execute(text(
                "ALTER TABLE settings ADD COLUMN IF NOT EXISTS r2_object_key VARCHAR(255)"
            ))
            
            # Create IPQS API keys table for multiple keys with usage tracking
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ipqs_api_keys (
                    id SERIAL PRIMARY KEY,
                    label VARCHAR(100) NOT NULL,
                    api_key VARCHAR(255) NOT NULL,
                    request_limit INTEGER DEFAULT 1000,
                    usage_count INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    last_used_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_ipqs_keys_active ON ipqs_api_keys(is_active)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_ipqs_keys_usage ON ipqs_api_keys(usage_count, is_active)"
            ))
            
            logger.info("Database migrations completed successfully")
        except Exception as e:
            logger.error(f"Error running migrations: {e}")

async def init_db():
    """Initialize database tables"""
    # Import models to ensure they are registered
    from bot import models  # noqa: F401
    
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        logger.info("Database initialized successfully")
    except Exception as e:
        # Tables might already exist, which is fine
        logger.info(f"Database tables already exist or initialization skipped: {e}")
    
    await run_migrations()
    await create_default_admin()
    await create_default_api_keys()
    await create_default_settings()

async def close_db():
    """Close database connection"""
    await engine.dispose()
    logger.info("Database connection closed")