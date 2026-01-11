"""Security utilities for CSRF protection, rate limiting, and input validation"""
from quart import request, session, abort
from functools import wraps
from secrets import token_urlsafe
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from bot.database import AsyncSessionLocal
from bot.models import RateLimit, Settings
from sqlalchemy import select, delete
import re
import html
from typing import Optional
import ipaddress
from urllib.parse import urlparse
import socket

# Legacy rate limiting storage (deprecated - use database-backed rate limiting)
# Kept for backward compatibility with in-memory fallback
rate_limit_storage = defaultdict(list)

def generate_csrf_token() -> str:
    """Generate a new CSRF token and store it in the session"""
    token = token_urlsafe(32)
    session['csrf_token'] = token
    return token

def get_csrf_token() -> Optional[str]:
    """Get the CSRF token from the session, create one if it doesn't exist"""
    if 'csrf_token' not in session:
        return generate_csrf_token()
    return session.get('csrf_token')

def validate_csrf_token(token: str) -> bool:
    """Validate a CSRF token against the session token"""
    session_token = session.get('csrf_token')
    if not session_token or not token:
        return False
    return session_token == token

def csrf_protect(func):
    """Decorator to protect routes from CSRF attacks"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            form_data = await request.form
            token = form_data.get('csrf_token') or request.headers.get('X-CSRF-Token') or ""
            
            if not validate_csrf_token(token):
                abort(403, 'Invalid CSRF token')
        
        return await func(*args, **kwargs)
    return wrapper

def rate_limit(max_requests: int = 5, window_seconds: int = 60):
    """
    Database-backed rate limiting decorator for distributed systems
    
    Args:
        max_requests: Maximum number of requests allowed
        window_seconds: Time window in seconds
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get real client IP from headers (handles proxies/load balancers)
            forwarded_for = request.headers.get('X-Forwarded-For', '').strip()
            if forwarded_for:
                # Take the first IP in the chain (the original client)
                client_ip = forwarded_for.split(',')[0].strip()
            else:
                client_ip = request.remote_addr or 'unknown'
            
            endpoint = request.endpoint
            key = f"{client_ip}:{endpoint}"
            
            # Use timezone-aware datetime for database compatibility
            now = datetime.now(timezone.utc)
            cutoff_time = now - timedelta(seconds=window_seconds)
            
            # Use database-backed rate limiting for multi-worker support
            async with AsyncSessionLocal() as db_session:
                try:
                    # Use PostgreSQL advisory lock to serialize rate limit checks for this key
                    # Generate a consistent hash for the key to use as lock ID
                    import hashlib
                    from sqlalchemy import text
                    lock_id = int(hashlib.md5(key.encode()).hexdigest()[:15], 16) % (2**31 - 1)
                    
                    # Acquire advisory lock (blocks concurrent requests for same key)
                    await db_session.execute(text(f"SELECT pg_advisory_lock({lock_id})"))
                    
                    try:
                        # Clean old rate limit records
                        await db_session.execute(
                            delete(RateLimit).where(
                                RateLimit.key == key,
                                RateLimit.request_time < cutoff_time
                            )
                        )
                        
                        # Count recent requests (now serialized by advisory lock)
                        result = await db_session.execute(
                            select(RateLimit).where(
                                RateLimit.key == key,
                                RateLimit.request_time >= cutoff_time
                            )
                        )
                        recent_requests = result.scalars().all()
                        
                        # Check rate limit
                        if len(recent_requests) >= max_requests:
                            abort(429, 'Too many requests. Please try again later.')
                        
                        # Record this request
                        rate_limit_record = RateLimit(
                            key=key,
                            request_time=now
                        )
                        db_session.add(rate_limit_record)
                        await db_session.commit()
                    finally:
                        # Always release advisory lock
                        await db_session.execute(text(f"SELECT pg_advisory_unlock({lock_id})"))
                    
                except Exception as e:
                    await db_session.rollback()
                    # Fallback to in-memory rate limiting on database errors
                    rate_limit_storage[key] = [
                        req_time for req_time in rate_limit_storage[key]
                        if req_time > cutoff_time
                    ]
                    
                    if len(rate_limit_storage[key]) >= max_requests:
                        abort(429, 'Too many requests. Please try again later.')
                    
                    rate_limit_storage[key].append(now)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    Sanitize user input to prevent XSS attacks
    
    Args:
        text: The text to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    # Truncate to max length
    text = text[:max_length]
    
    # HTML escape to prevent XSS
    text = html.escape(text)
    
    # Remove any null bytes
    text = text.replace('\x00', '')
    
    return text.strip()

def is_strong_password(password: str) -> tuple[bool, str]:
    """
    Check if a password meets security requirements
    
    Returns:
        (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if len(password) > 128:
        return False, "Password must not exceed 128 characters"
    
    # Check for at least one uppercase letter
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    # Check for at least one lowercase letter
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    # Check for at least one digit
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    # Check for at least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;/]', password):
        return False, "Password must contain at least one special character (!@#$%^&*...)"
    
    # Check for common weak passwords
    weak_passwords = [
        'password', 'Password1!', '12345678', 'admin123', 
        'qwerty123', 'Password123!', 'Admin123!', 'Welcome1!'
    ]
    if password in weak_passwords:
        return False, "This password is too common. Please choose a stronger password"
    
    return True, ""

def validate_email_format(email: str) -> bool:
    """
    Validate email format
    
    Args:
        email: Email address to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not email or len(email) > 254:
        return False
    
    # RFC 5322 compliant email regex (simplified)
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def normalize_email(email: str) -> str:
    """
    Normalize email address to prevent duplicates
    
    Args:
        email: Email address to normalize
    
    Returns:
        Normalized email in lowercase
    """
    return email.lower().strip()

def validate_url(url: str) -> bool:
    """
    Validate URL format for traffic source
    
    Args:
        url: URL to validate
    
    Returns:
        True if valid URL format
    """
    if not url:
        return False
    
    # Basic URL pattern
    pattern = r'^https?://[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?(\.[a-zA-Z0-9][a-zA-Z0-9-]{0,61}[a-zA-Z0-9]?)*(:[0-9]{1,5})?(/.*)?$'
    return bool(re.match(pattern, url))

def validate_callback_url(url: str) -> tuple[bool, str]:
    """
    Validate callback URL and prevent SSRF attacks
    
    Args:
        url: Callback URL to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return True, ""  # Empty URL is allowed
    
    # Check basic URL format
    if not validate_url(url):
        return False, "Invalid URL format"
    
    # Parse the URL
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Failed to parse URL"
    
    # Only allow HTTP and HTTPS
    if parsed.scheme not in ['http', 'https']:
        return False, "Only HTTP and HTTPS protocols are allowed"
    
    # Require HTTPS in production
    from os import environ
    if environ.get('ENVIRONMENT', 'production') == 'production' and parsed.scheme != 'https':
        return False, "HTTPS required for callback URLs in production"
    
    # Block localhost and private IP addresses to prevent SSRF
    hostname = parsed.hostname
    if not hostname:
        return False, "Invalid hostname"
    
    # Block localhost variations
    if hostname.lower() in ['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]']:
        return False, "Callback URL cannot target localhost"
    
    # Try to resolve hostname to IP and check if it's private
    try:
        ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip)
        
        # Block private, loopback, link-local, and multicast addresses
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast:
            return False, "Callback URL cannot target internal/private networks"
        
        # Block reserved addresses
        if ip_obj.is_reserved:
            return False, "Callback URL cannot target reserved IP addresses"
            
    except socket.gaierror:
        # Cannot resolve hostname - might be invalid or DNS issues
        # Allow it but log it
        pass
    except ValueError:
        # Invalid IP address format
        pass
    
    return True, ""

def api_rate_limit(func):
    """
    Database-backed API rate limiting with configurable limits from Settings
    Reads api_rate_limit and api_rate_window from the Settings table
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Get real client IP from headers (handles proxies/load balancers)
        forwarded_for = request.headers.get('X-Forwarded-For', '').strip()
        if forwarded_for:
            # Take the first IP in the chain (the original client)
            client_ip = forwarded_for.split(',')[0].strip()
        else:
            client_ip = request.remote_addr or 'unknown'
        
        endpoint = request.endpoint
        key = f"{client_ip}:{endpoint}"
        
        # Use timezone-aware datetime for database compatibility
        now = datetime.now(timezone.utc)
        
        # Use database-backed rate limiting for multi-worker support
        async with AsyncSessionLocal() as db_session:
            try:
                # Fetch settings for API rate limits
                settings_result = await db_session.execute(select(Settings))
                settings = settings_result.scalar_one_or_none()
                
                if settings:
                    max_requests = settings.api_rate_limit
                    window_seconds = settings.api_rate_window
                else:
                    # Default values if settings not found
                    max_requests = 100
                    window_seconds = 3600
                
                cutoff_time = now - timedelta(seconds=window_seconds)
                
                # Use PostgreSQL advisory lock to serialize rate limit checks for this key
                # Generate a consistent hash for the key to use as lock ID
                import hashlib
                from sqlalchemy import text
                lock_id = int(hashlib.md5(key.encode()).hexdigest()[:15], 16) % (2**31 - 1)
                
                # Acquire advisory lock (blocks concurrent requests for same key)
                await db_session.execute(text(f"SELECT pg_advisory_lock({lock_id})"))
                
                try:
                    # Clean old rate limit records
                    await db_session.execute(
                        delete(RateLimit).where(
                            RateLimit.key == key,
                            RateLimit.request_time < cutoff_time
                        )
                    )
                    
                    # Count recent requests (now serialized by advisory lock)
                    result = await db_session.execute(
                        select(RateLimit).where(
                            RateLimit.key == key,
                            RateLimit.request_time >= cutoff_time
                        )
                    )
                    recent_requests = result.scalars().all()
                    
                    # Check rate limit
                    if len(recent_requests) >= max_requests:
                        abort(429, 'Too many requests. Please try again later.')
                    
                    # Record this request
                    rate_limit_record = RateLimit(
                        key=key,
                        request_time=now
                    )
                    db_session.add(rate_limit_record)
                    await db_session.commit()
                finally:
                    # Always release advisory lock
                    await db_session.execute(text(f"SELECT pg_advisory_unlock({lock_id})"))
                
            except Exception as e:
                await db_session.rollback()
                # Fallback to in-memory rate limiting on database errors
                max_requests = 100
                window_seconds = 3600
                cutoff_time = now - timedelta(seconds=window_seconds)
                
                rate_limit_storage[key] = [
                    req_time for req_time in rate_limit_storage[key]
                    if req_time > cutoff_time
                ]
                
                if len(rate_limit_storage[key]) >= max_requests:
                    abort(429, 'Too many requests. Please try again later.')
                
                rate_limit_storage[key].append(now)
        
        return await func(*args, **kwargs)
    return wrapper
