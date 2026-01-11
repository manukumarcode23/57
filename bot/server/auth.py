from quart import Blueprint, request, render_template, redirect, session, jsonify, url_for
from bot.database import AsyncSessionLocal
from bot.models import Publisher, PublisherRegistration, PublisherLoginEvent, ReferralSettings
from sqlalchemy import select
from datetime import datetime, timezone
import bcrypt
import re
from .security import (
    csrf_protect, rate_limit, get_csrf_token,
    is_strong_password, validate_email_format, normalize_email,
    sanitize_input, validate_url
)
from bot.modules.geoip import get_location_from_ip
from bot.modules.device_detection import parse_user_agent, generate_device_fingerprint, generate_hardware_fingerprint, validate_fingerprint_data
from .referral_helper import validate_referral_code, create_referral_relationship, create_referral_code_for_publisher
from .encryption import get_public_key, decrypt_json

bp = Blueprint('auth', __name__)

def regenerate_session():
    """
    Regenerate session to prevent session fixation attacks.
    Clears all session data and generates a new session ID.
    """
    csrf_token = session.get('csrf_token')
    session.clear()
    if csrf_token:
        session['csrf_token'] = csrf_token

def is_valid_email(email: str) -> bool:
    return validate_email_format(email)

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def get_client_ip() -> str:
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    return request.remote_addr or '127.0.0.1'

def get_user_agent() -> str:
    return request.headers.get('User-Agent', 'Unknown')

@bp.route('/register', methods=['GET'])
async def register_page():
    if 'publisher_id' in session:
        if 'pending_referral_code' in session:
            del session['pending_referral_code']
        if session.get('is_admin', False):
            return redirect('/admin/dashboard')
        else:
            return redirect('/publisher/dashboard')
    
    referral_code = request.args.get('ref', '').strip().upper()
    if not referral_code:
        referral_code = request.args.get('referral', '').strip().upper()
    
    if referral_code:
        session['pending_referral_code'] = referral_code
    
    csrf_token = get_csrf_token()
    return await render_template('register.html', csrf_token=csrf_token)

@bp.route('/register', methods=['POST'])
@csrf_protect
@rate_limit(max_requests=3, window_seconds=300)
async def register():
    data = await request.form
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')
    traffic_source = data.get('traffic_source', '').strip()
    
    referral_code = session.get('pending_referral_code', '').strip().upper()
    
    csrf_token = get_csrf_token()
    
    import logging
    logger = logging.getLogger('bot')
    logger.info(f"Registration attempt - Referral code from session: {referral_code if referral_code else 'None'}")
    
    if not all([email, password, confirm_password, traffic_source]):
        return await render_template('register.html', error='All fields are required', csrf_token=csrf_token)
    
    if not is_valid_email(email):
        return await render_template('register.html', error='Invalid email format', csrf_token=csrf_token)
    
    if len(email) > 254:
        return await render_template('register.html', error='Email address is too long', csrf_token=csrf_token)
    
    if password != confirm_password:
        return await render_template('register.html', error='Passwords do not match', csrf_token=csrf_token)
    
    is_valid, password_error = is_strong_password(password)
    if not is_valid:
        return await render_template('register.html', error=password_error, csrf_token=csrf_token)
    
    if not validate_url(traffic_source) and not traffic_source.startswith('@'):
        return await render_template('register.html', error='Please provide a valid URL or social media handle (e.g., https://example.com or @username)', csrf_token=csrf_token)
    
    if referral_code:
        code_valid, referrer_id = await validate_referral_code(referral_code)
        if not code_valid:
            return await render_template('register.html', error='Invalid referral code', csrf_token=csrf_token)
    
    normalized_email = normalize_email(email)
    sanitized_traffic_source = sanitize_input(traffic_source, max_length=500)
    
    async with AsyncSessionLocal() as db_session:
        try:
            from sqlalchemy import func
            result = await db_session.execute(
                select(Publisher).where(func.lower(Publisher.email) == normalized_email)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                return await render_template('register.html', error='Email already registered', csrf_token=csrf_token)
            
            password_hash = hash_password(password)
            
            publisher = Publisher(
                email=normalized_email,
                password_hash=password_hash,
                traffic_source=sanitized_traffic_source,
                is_admin=False,
                is_active=True
            )
            
            db_session.add(publisher)
            await db_session.commit()
            await db_session.refresh(publisher)
            
            client_ip = get_client_ip()
            user_agent = get_user_agent()
            country_code, country_name, region = await get_location_from_ip(client_ip)
            
            device_info = parse_user_agent(user_agent)
            
            # Collect SERVER-SIDE request headers for fingerprinting (secure, cannot be manipulated)
            request_headers = dict(request.headers)
            
            # Generate fingerprints using SERVER-SIDE data only
            device_fingerprint = generate_device_fingerprint(client_ip, user_agent, request_headers)
            hardware_fingerprint = generate_hardware_fingerprint(user_agent, request_headers)
            
            registration_log = PublisherRegistration(
                publisher_id=publisher.id,
                email=normalized_email,
                traffic_source=sanitized_traffic_source,
                ip_address=client_ip,
                user_agent=user_agent,
                country_code=country_code,
                country_name=country_name,
                device_fingerprint=device_fingerprint,
                hardware_fingerprint=hardware_fingerprint,
                device_type=device_info.get('device_type'),
                device_name=device_info.get('device_name'),
                operating_system=device_info.get('operating_system'),
                browser_name=device_info.get('browser_name'),
                browser_version=device_info.get('browser_version')
            )
            db_session.add(registration_log)
            await db_session.commit()
            
            await create_referral_code_for_publisher(publisher.id)
            
            if referral_code:
                logger.info(f"Processing referral code: {referral_code}")
                code_valid, referrer_id = await validate_referral_code(referral_code)
                logger.info(f"Referral code validation result: valid={code_valid}, referrer_id={referrer_id}")
                if code_valid and referrer_id:
                    result = await create_referral_relationship(referrer_id, publisher.id, referral_code)
                    logger.info(f"Referral relationship created: {result}")
                else:
                    logger.warning(f"Referral code {referral_code} failed validation on second check")
            else:
                settings_result = await db_session.execute(select(ReferralSettings))
                settings = settings_result.scalar_one_or_none()
                
                if settings and settings.new_publisher_welcome_bonus_enabled and settings.new_publisher_welcome_bonus_amount > 0:
                    publisher.balance += settings.new_publisher_welcome_bonus_amount
                    await db_session.commit()
                    logger.info(f"Credited welcome bonus of ${settings.new_publisher_welcome_bonus_amount} to new publisher {publisher.id} (no referral code)")
            
            if 'pending_referral_code' in session:
                del session['pending_referral_code']
            
            regenerate_session()
            
            session['publisher_id'] = publisher.id
            session['publisher_email'] = publisher.email
            session['is_admin'] = publisher.is_admin
            session.permanent = True
            
            return redirect('/publisher/dashboard')
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Registration failed: {str(e)}", exc_info=True)
            return await render_template('register.html', error='Registration failed. Please try again.', csrf_token=csrf_token)

@bp.route('/login', methods=['GET'])
async def login_page():
    if 'publisher_id' in session:
        if session.get('is_admin', False):
            return redirect('/admin/dashboard')
        else:
            return redirect('/publisher/dashboard')
    csrf_token = get_csrf_token()
    
    public_key = get_public_key()
    
    return await render_template('login.html', csrf_token=csrf_token, public_key=public_key)

@bp.route('/login', methods=['POST'])
@csrf_protect
@rate_limit(max_requests=5, window_seconds=300)
async def login():
    data = await request.form
    encrypted_data = data.get('encrypted_data', '').strip()
    
    csrf_token = get_csrf_token()
    public_key = get_public_key()
    
    if not encrypted_data:
        return await render_template('login.html', error='Encrypted data required. Please enable JavaScript.', csrf_token=csrf_token, public_key=public_key)
    
    try:
        decrypted = decrypt_json(encrypted_data)
        email = decrypted.get('email', '').strip()
        password = decrypted.get('password', '')
    except Exception as e:
        import logging
        logger = logging.getLogger('bot')
        logger.error(f"Decryption failed: {str(e)}")
        return await render_template('login.html', error='Invalid encrypted data. Please refresh and try again.', csrf_token=csrf_token, public_key=public_key)
    
    if not email or not password:
        return await render_template('login.html', error='Email and password are required', csrf_token=csrf_token, public_key=public_key)
    
    normalized_email = normalize_email(email)
    
    client_ip = get_client_ip()
    user_agent = get_user_agent()
    country_code, country_name, region = await get_location_from_ip(client_ip)
    
    device_info = parse_user_agent(user_agent)
    
    # Collect SERVER-SIDE request headers for fingerprinting (secure, cannot be manipulated)
    import logging
    logger = logging.getLogger('bot')
    request_headers = dict(request.headers)
    
    # Generate fingerprints using SERVER-SIDE data only
    device_fingerprint = generate_device_fingerprint(client_ip, user_agent, request_headers)
    hardware_fingerprint = generate_hardware_fingerprint(user_agent, request_headers)
    
    async with AsyncSessionLocal() as db_session:
        try:
            from sqlalchemy import func
            result = await db_session.execute(
                select(Publisher).where(func.lower(Publisher.email) == normalized_email)
            )
            publisher = result.scalar_one_or_none()
            
            if not publisher:
                login_event = PublisherLoginEvent(
                    publisher_id=None,
                    email=normalized_email,
                    success=False,
                    failure_reason='Invalid credentials',
                    ip_address=client_ip,
                    user_agent=user_agent,
                    country_code=country_code,
                    country_name=country_name,
                    device_fingerprint=device_fingerprint,
                    hardware_fingerprint=hardware_fingerprint,
                    device_type=device_info.get('device_type'),
                    device_name=device_info.get('device_name'),
                    operating_system=device_info.get('operating_system'),
                    browser_name=device_info.get('browser_name'),
                    browser_version=device_info.get('browser_version')
                )
                db_session.add(login_event)
                await db_session.commit()
                return await render_template('login.html', error='Invalid email or password', csrf_token=csrf_token, public_key=public_key)
            
            if not publisher.is_active:
                login_event = PublisherLoginEvent(
                    publisher_id=publisher.id,
                    email=normalized_email,
                    success=False,
                    failure_reason='Account disabled',
                    ip_address=client_ip,
                    user_agent=user_agent,
                    country_code=country_code,
                    country_name=country_name,
                    device_fingerprint=device_fingerprint,
                    hardware_fingerprint=hardware_fingerprint,
                    device_type=device_info.get('device_type'),
                    device_name=device_info.get('device_name'),
                    operating_system=device_info.get('operating_system'),
                    browser_name=device_info.get('browser_name'),
                    browser_version=device_info.get('browser_version')
                )
                db_session.add(login_event)
                await db_session.commit()
                return await render_template('login.html', error='Account is disabled. Please contact support.', csrf_token=csrf_token, public_key=public_key)
            
            if not verify_password(password, publisher.password_hash):
                login_event = PublisherLoginEvent(
                    publisher_id=publisher.id,
                    email=normalized_email,
                    success=False,
                    failure_reason='Invalid password',
                    ip_address=client_ip,
                    user_agent=user_agent,
                    country_code=country_code,
                    country_name=country_name,
                    device_fingerprint=device_fingerprint,
                    hardware_fingerprint=hardware_fingerprint,
                    device_type=device_info.get('device_type'),
                    device_name=device_info.get('device_name'),
                    operating_system=device_info.get('operating_system'),
                    browser_name=device_info.get('browser_name'),
                    browser_version=device_info.get('browser_version')
                )
                db_session.add(login_event)
                await db_session.commit()
                return await render_template('login.html', error='Invalid email or password', csrf_token=csrf_token, public_key=public_key)
            
            publisher.last_login = datetime.now(timezone.utc)
            publisher.last_login_ip = client_ip
            publisher.last_login_geo = f"{country_name} ({country_code})" if country_name else None
            
            login_event = PublisherLoginEvent(
                publisher_id=publisher.id,
                email=normalized_email,
                success=True,
                failure_reason=None,
                ip_address=client_ip,
                user_agent=user_agent,
                country_code=country_code,
                country_name=country_name,
                device_fingerprint=device_fingerprint,
                hardware_fingerprint=hardware_fingerprint,
                device_type=device_info.get('device_type'),
                device_name=device_info.get('device_name'),
                operating_system=device_info.get('operating_system'),
                browser_name=device_info.get('browser_name'),
                browser_version=device_info.get('browser_version')
            )
            db_session.add(login_event)
            await db_session.commit()
            
            regenerate_session()
            
            session['publisher_id'] = publisher.id
            session['publisher_email'] = publisher.email
            session['is_admin'] = publisher.is_admin
            session.permanent = True
            
            if publisher.is_admin:
                return redirect('/admin/dashboard')
            else:
                return redirect('/publisher/dashboard')
            
        except Exception as e:
            await db_session.rollback()
            return await render_template('login.html', error='Login failed. Please try again.', csrf_token=csrf_token, public_key=public_key)

@bp.route('/logout')
async def logout():
    session.clear()
    return redirect('/login')
