from sqlalchemy import String, BigInteger, DateTime, Text, Boolean, Integer, Date, Float, CheckConstraint, Index, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from bot.database import Base
from datetime import datetime, date
from typing import Optional

class File(Base):
    """Model for storing file information"""
    __tablename__ = "files"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(100))
    access_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    video_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_file_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    temporary_stream_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)
    temporary_download_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)
    link_expiry_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by_android_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    publisher_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='SET NULL'), nullable=True, index=True)
    custom_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    r2_object_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

class User(Base):
    """Model for storing user information"""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50), nullable=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=False)

class AccessLog(Base):
    """Model for logging file access"""
    __tablename__ = "access_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('files.id', ondelete='CASCADE'), index=True)
    user_ip: Mapped[str] = mapped_column(String(45))  # IPv6 support
    user_agent: Mapped[str] = mapped_column(Text, nullable=True)
    access_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, default=True)

class DeviceLink(Base):
    """Model for storing device-specific streaming and download links"""
    __tablename__ = "device_links"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('files.id', ondelete='CASCADE'), index=True)
    android_id: Mapped[str] = mapped_column(String(100), index=True)
    hash_id: Mapped[str] = mapped_column(String(32), index=True)
    stream_token: Mapped[str] = mapped_column(String(64), index=True)
    download_token: Mapped[str] = mapped_column(String(64), index=True)
    link_expiry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class LinkTransaction(Base):
    """Model for tracking link delivery to external API"""
    __tablename__ = "link_transactions"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('files.id', ondelete='CASCADE'), index=True)
    android_id: Mapped[str] = mapped_column(String(100), index=True)
    hash_id: Mapped[str] = mapped_column(String(32), index=True)
    stream_link: Mapped[str] = mapped_column(Text)
    download_link: Mapped[str] = mapped_column(Text)
    callback_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    callback_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    callback_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    callback_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)

class Publisher(Base):
    """Model for storing publisher information"""
    __tablename__ = "publishers"
    __table_args__ = (
        CheckConstraint('balance >= 0', name='check_balance_non_negative'),
        CheckConstraint('custom_impression_rate IS NULL OR custom_impression_rate >= 0', name='check_custom_rate_non_negative'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    traffic_source: Mapped[str] = mapped_column(Text)
    api_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)
    telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, unique=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    custom_impression_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    thumbnail_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    thumbnail_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default=None)
    logo_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    default_video_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    last_login_geo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

class AdMobSettings(Base):
    """Model for storing AdMob ads settings"""
    __tablename__ = "admob_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    rewarded_ad_unit: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rewarded_api_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    banner_ad_unit: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    banner_api_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interstitial_ad_unit: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    interstitial_api_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AdNetwork(Base):
    """Model for storing multiple ad network configurations"""
    __tablename__ = "ad_networks"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    network_name: Mapped[str] = mapped_column(String(100), index=True)
    banner_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    interstitial_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rewarded_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    banner_daily_limit: Mapped[int] = mapped_column(Integer, default=0)
    interstitial_daily_limit: Mapped[int] = mapped_column(Integer, default=0)
    rewarded_daily_limit: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default='active')
    priority: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AdPlayCount(Base):
    """Model for tracking daily ad play counts per user"""
    __tablename__ = "ad_play_counts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    ad_network_id: Mapped[int] = mapped_column(Integer, ForeignKey('ad_networks.id', ondelete='CASCADE'), index=True)
    ad_type: Mapped[str] = mapped_column(String(20), index=True)
    android_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    user_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, index=True)
    play_date: Mapped[date] = mapped_column(Date, index=True, server_default=func.current_date())
    play_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AdPlayTracking(Base):
    """Model for tracking individual ad plays with unique tokens"""
    __tablename__ = "ad_play_tracking"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ad_network_id: Mapped[int] = mapped_column(Integer, ForeignKey('ad_networks.id', ondelete='CASCADE'), index=True)
    network_name: Mapped[str] = mapped_column(String(100))
    ad_type: Mapped[str] = mapped_column(String(20), index=True)
    ad_unit_id: Mapped[str] = mapped_column(String(255))
    android_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    user_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    country_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_played: Mapped[bool] = mapped_column(Boolean, default=False)
    played_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class PublisherImpression(Base):
    """Model for tracking publisher video impressions"""
    __tablename__ = "publisher_impressions"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    hash_id: Mapped[str] = mapped_column(String(32), index=True)
    android_id: Mapped[str] = mapped_column(String(255), index=True)
    user_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True, index=True)
    country_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    impression_date: Mapped[date] = mapped_column(Date, index=True, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Settings(Base):
    """Model for storing application settings"""
    __tablename__ = "settings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    terms_of_service: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    privacy_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    impression_rate: Mapped[float] = mapped_column(Float, default=0.0)
    impression_cutback_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    android_package_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    android_deep_link_scheme: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    minimum_withdrawal: Mapped[float] = mapped_column(Float, default=10.0)
    callback_mode: Mapped[str] = mapped_column(String(10), default='POST')
    web_max_file_size_mb: Mapped[int] = mapped_column(Integer, default=2048)
    web_upload_rate_limit: Mapped[int] = mapped_column(Integer, default=10)
    web_upload_rate_window: Mapped[int] = mapped_column(Integer, default=3600)
    api_rate_limit: Mapped[int] = mapped_column(Integer, default=100)
    api_rate_window: Mapped[int] = mapped_column(Integer, default=3600)
    logo_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    favicon_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    default_thumbnail_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    withdrawal_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    subscriptions_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    web_publisher_subscriptions_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    paytm_mid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paytm_upi_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paytm_unit_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    paytm_signature: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    global_api_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ads_api_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    payment_api_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ipqs_api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ipqs_secret_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ipqs_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    r2_storage_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    r2_object_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    terabox_domains: Mapped[str] = mapped_column(Text, default="terabox.com,1024tera.com,terasharefile.com")
    terabox_api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website_name: Mapped[str] = mapped_column(String(100), default="CloudShare Pro")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class BankAccount(Base):
    """Model for storing publisher bank account and crypto wallet information"""
    __tablename__ = "bank_accounts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    account_holder_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bank_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ifsc_code: Mapped[Optional[str]] = mapped_column(String(11), nullable=True)
    branch_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="India")
    trc20_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bep20_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class WithdrawalRequest(Base):
    """Model for tracking publisher withdrawal requests"""
    __tablename__ = "withdrawal_requests"
    __table_args__ = (
        Index('idx_withdrawal_publisher_status', 'publisher_id', 'status'),
        Index('idx_withdrawal_status_requested', 'status', 'requested_at'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    bank_account_id: Mapped[int] = mapped_column(Integer, ForeignKey('bank_accounts.id', ondelete='RESTRICT'), index=True)
    amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class Bot(Base):
    """Model for storing bot information for publishers"""
    __tablename__ = "bots"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_name: Mapped[str] = mapped_column(String(255))
    bot_link: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class CountryRate(Base):
    """Model for storing country-specific impression rates"""
    __tablename__ = "country_rates"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), unique=True, index=True)
    country_name: Mapped[str] = mapped_column(String(100))
    impression_rate: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Ticket(Base):
    """Model for storing support tickets"""
    __tablename__ = "tickets"
    __table_args__ = (
        Index('idx_ticket_publisher_status', 'publisher_id', 'status'),
        Index('idx_ticket_status_created', 'status', 'created_at'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='open', index=True)
    priority: Mapped[str] = mapped_column(String(20), default='normal')
    admin_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class RateLimit(Base):
    """Model for distributed rate limiting across multiple workers"""
    __tablename__ = "rate_limits"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255), index=True)
    request_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ImpressionAdjustment(Base):
    """Model for tracking manual impression adjustments by admin"""
    __tablename__ = "impression_adjustments"
    __table_args__ = (
        Index('idx_adjustment_publisher_created', 'publisher_id', 'created_at'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    adjustment_type: Mapped[str] = mapped_column(String(20))  # 'add' or 'deduct'
    amount: Mapped[int] = mapped_column(Integer)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_email: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PublisherRegistration(Base):
    """Model for tracking publisher registrations"""
    __tablename__ = "publisher_registrations"
    __table_args__ = (
        Index('idx_registration_ip_created', 'ip_address', 'created_at'),
        Index('idx_registration_publisher', 'publisher_id', 'created_at'),
        Index('idx_registration_fingerprint', 'device_fingerprint', 'created_at'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    email: Mapped[str] = mapped_column(String(255))
    traffic_source: Mapped[str] = mapped_column(Text)
    ip_address: Mapped[str] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    country_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    hardware_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    operating_system: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    browser_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    browser_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

class PublisherLoginEvent(Base):
    """Model for tracking publisher login attempts"""
    __tablename__ = "publisher_login_events"
    __table_args__ = (
        Index('idx_login_ip_created', 'ip_address', 'created_at'),
        Index('idx_login_publisher_created', 'publisher_id', 'created_at'),
        Index('idx_login_success_created', 'success', 'created_at'),
        Index('idx_login_fingerprint', 'device_fingerprint', 'created_at'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='SET NULL'), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255))
    success: Mapped[bool] = mapped_column(Boolean, index=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    country_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    hardware_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    device_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    operating_system: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    browser_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    browser_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

class PublisherAccountLink(Base):
    """Model for tracking suspected multi-account relationships"""
    __tablename__ = "publisher_account_links"
    __table_args__ = (
        Index('idx_account_link_cluster', 'cluster_id', 'created_at'),
        Index('idx_account_link_publisher', 'publisher_id', 'confidence'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[str] = mapped_column(String(64), index=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    related_publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    relationship_reason: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

class ReferralSettings(Base):
    """Model for storing referral system configuration"""
    __tablename__ = "referral_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reward_on_registration: Mapped[bool] = mapped_column(Boolean, default=False)
    registration_reward_amount: Mapped[float] = mapped_column(Float, default=0.0)
    new_publisher_welcome_bonus_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    new_publisher_welcome_bonus_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reward_on_first_withdrawal: Mapped[bool] = mapped_column(Boolean, default=True)
    first_withdrawal_reward_amount: Mapped[float] = mapped_column(Float, default=2.0)
    reward_on_second_withdrawal: Mapped[bool] = mapped_column(Boolean, default=True)
    second_withdrawal_reward_amount: Mapped[float] = mapped_column(Float, default=1.0)
    reward_on_third_withdrawal: Mapped[bool] = mapped_column(Boolean, default=False)
    third_withdrawal_reward_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reward_on_fourth_withdrawal: Mapped[bool] = mapped_column(Boolean, default=False)
    fourth_withdrawal_reward_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reward_on_fifth_withdrawal: Mapped[bool] = mapped_column(Boolean, default=False)
    fifth_withdrawal_reward_amount: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ReferralCode(Base):
    """Model for storing publisher referral codes"""
    __tablename__ = "referral_codes"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), unique=True, index=True)
    referral_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    total_referrals: Mapped[int] = mapped_column(Integer, default=0)
    total_earnings: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Referral(Base):
    """Model for tracking referral relationships"""
    __tablename__ = "referrals"
    __table_args__ = (
        Index('idx_referral_referrer_created', 'referrer_id', 'created_at'),
        Index('idx_referral_referred_status', 'referred_publisher_id', 'status'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    referred_publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), unique=True, index=True)
    referral_code: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    total_rewards_earned: Mapped[float] = mapped_column(Float, default=0.0)
    completed_withdrawals: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ReferralReward(Base):
    """Model for tracking individual referral rewards"""
    __tablename__ = "referral_rewards"
    __table_args__ = (
        Index('idx_reward_referral_milestone', 'referral_id', 'milestone_type'),
        Index('idx_reward_referrer_created', 'referrer_id', 'created_at'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    referral_id: Mapped[int] = mapped_column(Integer, ForeignKey('referrals.id', ondelete='CASCADE'), index=True)
    referrer_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    referred_publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    milestone_type: Mapped[str] = mapped_column(String(50))
    reward_amount: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    credited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawal_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('withdrawal_requests.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ApiEndpointKey(Base):
    """Model for storing API endpoint keys for secure access control"""
    __tablename__ = "api_endpoint_keys"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    endpoint_path: Mapped[str] = mapped_column(String(500))
    api_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class SubscriptionPlan(Base):
    """Model for storing subscription plans"""
    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint('earning_per_link IS NULL OR earning_per_link >= 0', name='check_earning_per_link_non_negative'),
        CheckConstraint('monthly_link_limit IS NULL OR monthly_link_limit >= 0', name='check_monthly_limit_non_negative'),
        Index('idx_plan_id_active', 'id', 'is_active'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    earning_per_link: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=0.0)
    monthly_link_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Subscription(Base):
    """Model for storing publisher subscriptions"""
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index('idx_subscription_publisher', 'publisher_id', 'status'),
        Index('idx_subscription_order', 'order_id'),
        Index('idx_subscription_android', 'android_id', 'status'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='SET NULL'), nullable=True, index=True)
    android_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    order_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('subscription_plans.id', ondelete='SET NULL'), nullable=True, index=True)
    plan_name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    payment_method: Mapped[str] = mapped_column(String(50), default='paytm')
    utr_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

class WebPublisherSubscriptionPlan(Base):
    """Model for storing web publisher subscription plans (for video upload feature)"""
    __tablename__ = "web_publisher_subscription_plans"
    __table_args__ = (
        Index('idx_web_plan_active', 'is_active'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer)
    upload_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    max_file_size_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=2048)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WebPublisherSubscription(Base):
    """Model for storing web publisher subscriptions (for video upload feature)"""
    __tablename__ = "web_publisher_subscriptions"
    __table_args__ = (
        Index('idx_web_sub_publisher', 'publisher_id', 'status'),
        Index('idx_web_sub_order', 'order_id'),
        Index('idx_web_sub_expires', 'publisher_id', 'expires_at'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    order_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('web_publisher_subscription_plans.id', ondelete='SET NULL'), nullable=True, index=True)
    plan_name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    upload_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    max_file_size_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=2048)
    uploads_used: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    payment_method: Mapped[str] = mapped_column(String(50), default='paytm')
    utr_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class IPQSApiKey(Base):
    """Model for storing multiple IPQS API keys with usage tracking"""
    __tablename__ = "ipqs_api_keys"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(100), index=True)
    api_key: Mapped[str] = mapped_column(String(255))
    request_limit: Mapped[int] = mapped_column(Integer, default=1000)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PremiumLinkEarning(Base):
    """Model for tracking publisher earnings from premium user link generation"""
    __tablename__ = "premium_link_earnings"
    __table_args__ = (
        UniqueConstraint('publisher_id', 'android_id', 'hash_id', 'earning_date', name='uq_earning_daily'),
        Index('idx_earning_publisher_date', 'publisher_id', 'earning_date'),
        Index('idx_earning_android_date', 'android_id', 'earning_date'),
        Index('idx_earning_hash', 'hash_id', 'earning_date'),
        Index('idx_earning_plan', 'plan_id', 'earning_date'),
        Index('idx_earning_date', 'earning_date'),
        Index('idx_earning_publisher_created', 'publisher_id', 'created_at'),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True)
    publisher_id: Mapped[int] = mapped_column(Integer, ForeignKey('publishers.id', ondelete='CASCADE'), index=True)
    android_id: Mapped[str] = mapped_column(String(255), index=True)
    hash_id: Mapped[str] = mapped_column(String(32), index=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey('subscription_plans.id', ondelete='CASCADE'), index=True)
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey('subscriptions.id', ondelete='CASCADE'), index=True)
    earning_amount: Mapped[float] = mapped_column(Float)
    earning_date: Mapped[date] = mapped_column(Date, index=True, server_default=func.current_date())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CloudflareR2Settings(Base):
    """Model for storing Cloudflare R2 configuration for video storage"""
    __tablename__ = "cloudflare_r2_settings"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    bucket_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    access_key_id: Mapped[str] = mapped_column(String(255))
    secret_access_key: Mapped[str] = mapped_column(Text)
    account_id: Mapped[str] = mapped_column(String(255))
    endpoint_url: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(50), default='us-east-1')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

