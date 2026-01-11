from quart import Blueprint, Response, request, render_template, redirect, jsonify
from .error import abort
from bot import TelegramBot
from bot.config import Telegram, Server
from math import ceil, floor
from bot.modules.telegram import get_message, get_file_properties
from bot.modules.geoip import get_location_from_ip
from bot.modules.file_validator import validate_file_type, sanitize_filename
from bot.modules.advanced_security import ultra_secure_validation
from bot.database import AsyncSessionLocal
from bot.models import AccessLog, File, DeviceLink, LinkTransaction, PublisherImpression, Settings, Publisher, CountryRate, Subscription
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone
from secrets import token_hex
from bot.server.security import csrf_protect, rate_limit, api_rate_limit
from bot.server.api_auth import require_endpoint_api_key
from bot.server.earning_service import process_premium_link_earning
from bot.server.ipqs_service import verify_ip_quality, get_available_ipqs_key, increment_ipqs_key_usage
import httpx
import logging
import os
from pathlib import Path
import tempfile
import uuid
import re
import asyncio

bp = Blueprint('main', __name__)
logger = logging.getLogger('bot.server')

MAX_VIDEO_DURATION = 86400  # 24 hours in seconds

from bot.database import generate_unique_access_code

async def get_web_upload_limits():
    """Get web upload limits from settings"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Settings))
        settings = result.scalar_one_or_none()
        
        if settings:
            return {
                'max_file_size_bytes': settings.web_max_file_size_mb * 1024 * 1024,
                'rate_limit': settings.web_upload_rate_limit,
                'rate_window': settings.web_upload_rate_window
            }
        else:
            return {
                'max_file_size_bytes': 2048 * 1024 * 1024,
                'rate_limit': 10,
                'rate_window': 3600
            }

async def get_request_location():
    """Get country and region information from the current request's IP"""
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    x_real_ip = request.headers.get('X-Real-IP', '')
    cf_connecting_ip = request.headers.get('CF-Connecting-IP', '')
    
    if cf_connecting_ip:
        user_ip = cf_connecting_ip.strip()
    elif x_real_ip:
        user_ip = x_real_ip.strip()
    elif x_forwarded_for:
        user_ip = x_forwarded_for.split(',')[0].strip()
    else:
        user_ip = request.remote_addr or '0.0.0.0'
    
    country_code, country_name, region = await get_location_from_ip(user_ip)
    return {
        'country_code': country_code,
        'country_name': country_name,
        'region': region
    }

async def send_links_to_api(android_id: str, stream_link: str, download_link: str, callback_url: str, callback_method: str = 'POST') -> tuple[bool, int, str]:
    """Send generated links to external API using GET or POST method"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if callback_method.upper() == 'GET':
                params = {
                    'android_id': android_id,
                    'stream_link': stream_link,
                    'download_link': download_link
                }
                response = await client.get(callback_url, params=params)
            else:
                payload = {
                    'android_id': android_id,
                    'stream_link': stream_link,
                    'download_link': download_link
                }
                response = await client.post(callback_url, json=payload)
            
            success = 200 <= response.status_code < 300
            if not success:
                logger.warning(f"API callback ({callback_method}) failed with status {response.status_code}: {response.text}")
            return success, response.status_code, response.text
    except Exception as e:
        logger.error(f"Error sending links to API via {callback_method}: {e}")
        return False, 0, str(e)

async def log_access_attempt(file_id: int, user_ip: str, user_agent: str, success: bool):
    """Log file access attempt to database"""
    async with AsyncSessionLocal() as session:
        try:
            access_log = AccessLog(
                file_id=file_id,
                user_ip=user_ip,
                user_agent=user_agent or '',
                success=success
            )
            session.add(access_log)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Error logging access attempt: {e}")

def detect_file_type(mime_type: str, filename: str) -> str:
    """Detect file type based on MIME type or filename extension
    Returns one of: 'apk', 'zip', or 'video' (default)
    """
    mime_type_lower = mime_type.lower() if mime_type else ''
    filename_lower = filename.lower() if filename else ''
    
    if 'application/vnd.android.package-archive' in mime_type_lower or filename_lower.endswith('.apk'):
        return 'apk'
    elif 'application/zip' in mime_type_lower or 'application/x-zip' in mime_type_lower or filename_lower.endswith('.zip'):
        return 'zip'
    else:
        return 'video'

@bp.route('/')
async def home():
    return await render_template('index.html', bot_username=Telegram.BOT_USERNAME)


@bp.route('/upload', methods=['POST'])
@csrf_protect
async def handle_upload():
    temp_path = None
    try:
        limits = await get_web_upload_limits()
        
        # Enforce web upload rate limiting
        forwarded_for = request.headers.get('X-Forwarded-For', '').strip()
        if forwarded_for:
            client_ip = forwarded_for.split(',')[0].strip()
        else:
            client_ip = request.remote_addr or 'unknown'
        
        endpoint = request.endpoint
        key = f"{client_ip}:{endpoint}"
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(seconds=limits['rate_window'])
        
        async with AsyncSessionLocal() as rate_session:
            from bot.models import RateLimit
            try:
                await rate_session.execute(
                    delete(RateLimit).where(
                        RateLimit.key == key,
                        RateLimit.request_time < cutoff_time
                    )
                )
                
                result = await rate_session.execute(
                    select(RateLimit).where(
                        RateLimit.key == key,
                        RateLimit.request_time >= cutoff_time
                    )
                )
                recent_requests = result.scalars().all()
                
                if len(recent_requests) >= limits['rate_limit']:
                    await rate_session.rollback()
                    return jsonify({'status': 'error', 'message': 'Too many upload requests. Please try again later.'}), 429
                
                rate_limit_record = RateLimit(
                    key=key,
                    request_time=now
                )
                rate_session.add(rate_limit_record)
                await rate_session.commit()
            except Exception as e:
                await rate_session.rollback()
                logger.warning(f"Error checking rate limit: {e}")
        
        files = await request.files
        if 'file' not in files and 'video' not in files:
            return jsonify({'status': 'error', 'message': 'No file provided'}), 400
        
        uploaded_file = files.get('file') or files.get('video')
        if not uploaded_file or not uploaded_file.filename:
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400
        
        is_valid, error_msg = validate_file_type(uploaded_file.filename, uploaded_file.content_type)
        if not is_valid:
            return jsonify({'status': 'error', 'message': error_msg}), 400
        
        # Preserve original filename, only sanitize for security (no modification)
        safe_filename = sanitize_filename(uploaded_file.filename) or f'file_upload_{uuid.uuid4().hex[:8]}'
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'_{safe_filename}') as temp_file:
            temp_path = temp_file.name
        
        await uploaded_file.save(temp_path)
        
        # Use configurable web upload file size limit from database
        file_size = os.path.getsize(temp_path)
        if file_size > limits['max_file_size_bytes']:
            max_size_gb = limits['max_file_size_bytes'] / (1024 * 1024 * 1024)
            return jsonify({'status': 'error', 'message': f'File size exceeds {max_size_gb:.1f} GB limit'}), 400
        
        # ULTRA-SECURE VALIDATION: Read file chunk for deep security scanning
        logger.info(f"Performing ultra-secure validation for web upload: {safe_filename}")
        try:
            # Read first 2MB for security scanning (or full file if smaller)
            scan_size = min(file_size, 2 * 1024 * 1024)
            with open(temp_path, 'rb') as f:
                file_chunk = f.read(scan_size)
            
            # Perform multi-layer security validation
            is_valid, error_msg = await ultra_secure_validation(
                file_bytes=file_chunk,
                filename=safe_filename,
                mime_type=uploaded_file.content_type or 'application/octet-stream',
                file_size=file_size,
                publisher_id=0  # Web uploads don't have publisher_id
            )
            
            if not is_valid:
                logger.error(f"Ultra-secure validation failed for web upload {safe_filename}: {error_msg}")
                return jsonify({
                    'status': 'error',
                    'message': f'Security validation failed: {error_msg}'
                }), 400
                
            logger.info(f"Ultra-secure validation passed for web upload: {safe_filename}")
            
        except Exception as e:
            logger.error(f"Security validation error for web upload {safe_filename}: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Unable to perform security validation on your file'
            }), 500
        
        secret_code = await generate_unique_access_code()
        
        sent_message = await TelegramBot.send_file(
            entity=Telegram.CHANNEL_ID,
            file=temp_path,
            caption=f'`{secret_code}`'
        )
        
        # Validate sent_message is not None and extract message ID
        if not sent_message:
            logger.error("Failed to send file to Telegram - received None")
            return jsonify({'status': 'error', 'message': 'Upload failed'}), 500
        
        if isinstance(sent_message, list):
            sent_message = sent_message[0] if sent_message else None
            if not sent_message:
                logger.error("Empty message list returned from Telegram")
                return jsonify({'status': 'error', 'message': 'Upload failed'}), 500
        
        message_id = sent_message.id
        
        telegram_message = await get_message(message_id=message_id)
        if not telegram_message:
            logger.error(f"Could not retrieve message after upload: {message_id}")
            return jsonify({'status': 'error', 'message': 'Failed to retrieve uploaded file'}), 500
        
        # Use original safe_filename instead of extracting from Telegram to avoid temp prefix
        filename = safe_filename
        _, telegram_file_size, mime_type = get_file_properties(telegram_message)
        # Use actual file size from disk as it's more accurate
        file_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else telegram_file_size
        
        video_duration = None
        thumbnail_file_id = None
        
        if hasattr(telegram_message, 'video') and telegram_message.video:
            if hasattr(telegram_message.video, 'attributes'):
                for attr in telegram_message.video.attributes:
                    if hasattr(attr, 'duration'):
                        try:
                            video_duration = attr.duration  # type: ignore
                            break
                        except AttributeError:
                            pass
            # Extract thumbnail for video files
            if hasattr(telegram_message.video, 'thumbs') and telegram_message.video.thumbs:
                try:
                    # Use video ID for thumbnail reference (PhotoSize doesn't have file_id)
                    thumbnail_file_id = str(telegram_message.video.id) if hasattr(telegram_message.video, 'id') else None
                except Exception as e:
                    logger.debug(f"Could not extract thumbnail: {e}")
        elif hasattr(telegram_message, 'document') and telegram_message.document:
            if hasattr(telegram_message.document, 'attributes'):
                for attr in telegram_message.document.attributes:
                    if hasattr(attr, 'duration'):
                        try:
                            video_duration = attr.duration  # type: ignore
                            break
                        except AttributeError:
                            pass
            # Extract thumbnail for documents with video content
            if hasattr(telegram_message.document, 'thumbs') and telegram_message.document.thumbs:
                try:
                    # Use document ID for thumbnail reference (PhotoSize doesn't have file_id)
                    thumbnail_file_id = str(telegram_message.document.id) if hasattr(telegram_message.document, 'id') else None
                except Exception as e:
                    logger.debug(f"Could not extract thumbnail: {e}")
        
        async with AsyncSessionLocal() as session:
            try:
                file_record = File(
                    telegram_message_id=message_id,
                    filename=filename,
                    file_size=file_size,
                    mime_type=mime_type,
                    access_code=secret_code,
                    video_duration=int(video_duration) if video_duration else None,
                    thumbnail_file_id=thumbnail_file_id
                )
                session.add(file_record)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Error saving file to database: {e}")
                return jsonify({'status': 'error', 'message': 'Database error'}), 500
        
        logger.info(f"File uploaded via web: {filename}, hash_id: {secret_code}")
        
        play_link = f'{Server.BASE_URL}/play/{secret_code}'
        
        return jsonify({
            'status': 'success',
            'hash_id': secret_code,
            'play_link': play_link,
            'message': 'File uploaded successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
    finally:
        # Ensure temp file is cleaned up in ALL error paths
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Could not remove temp file: {e}")

@bp.route('/api/request', methods=['POST'])
@api_rate_limit
@require_endpoint_api_key('API Request')
async def request_links():
    data = await request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400
    android_id = data.get('android_id', '').strip()
    hash_id = data.get('hash_id', '').strip()
    
    if not android_id or not hash_id:
        return jsonify({'status': 'error', 'message': 'android_id and hash_id are required'}), 400
    
    if not re.match(r'^[a-fA-F0-9]{24}$', hash_id):
        return jsonify({'status': 'error', 'message': 'Invalid hash_id format'}), 400
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(File).where(File.access_code == hash_id)
        )
        file_record = result.scalar_one_or_none()
        
        if not file_record:
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        
        if not file_record.is_active:
            return jsonify({'status': 'error', 'message': 'File has been revoked'}), 403
        
        # Check if android_id has active subscription
        sub_result = await session.execute(
            select(Subscription).where(
                Subscription.android_id == android_id,
                Subscription.status == 'completed',
                (Subscription.expires_at.is_(None)) | (Subscription.expires_at > datetime.now(timezone.utc))
            ).order_by(Subscription.expires_at.desc())
        )
        subscription = sub_result.scalars().first()
        
        # If user has active subscription, generate links immediately
        if subscription:
            logger.info(f"Subscribed user (android_id: {android_id}) requesting file {hash_id}. Generating links directly.")
            
            # Delete any existing links for the same android_id and hash_id combination
            delete_stmt = delete(DeviceLink).where(
                DeviceLink.android_id == android_id,
                DeviceLink.hash_id == hash_id
            )
            await session.execute(delete_stmt)
            
            stream_token = token_hex(32)
            download_token = token_hex(32)
            
            if file_record.video_duration and 0 < file_record.video_duration <= MAX_VIDEO_DURATION:
                expiry_seconds = file_record.video_duration + 3600
            else:
                expiry_seconds = 7200
            
            expiry_time = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)
            
            device_link = DeviceLink(
                file_id=file_record.telegram_message_id,
                android_id=android_id,
                hash_id=hash_id,
                stream_token=stream_token,
                download_token=download_token,
                link_expiry_time=expiry_time
            )
            session.add(device_link)
            
            file_type = detect_file_type(file_record.mime_type, file_record.filename)
            
            # Check if R2 is enabled and we have an object key for this file
            from bot.modules.r2_storage import get_r2_download_url
            r2_url = await get_r2_download_url(file_record.r2_object_key, expires_in=expiry_seconds)
            
            # Priority: R2 URL if available, otherwise fallback to Telegram internal links
            if r2_url:
                stream_link = r2_url
                download_link = r2_url
                logger.info(f"Serving R2 links for hash_id {hash_id}")
            else:
                stream_link = f'{Server.BASE_URL}/stream/{file_record.telegram_message_id}?token={stream_token}'
                download_link = f'{Server.BASE_URL}/dl/{file_record.telegram_message_id}?token={download_token}&file_type={file_type}'
                logger.info(f"Serving Telegram links for hash_id {hash_id} (R2 not available)")
            
            transaction = LinkTransaction(
                file_id=file_record.telegram_message_id,
                android_id=android_id,
                hash_id=hash_id,
                stream_link=stream_link,
                download_link=download_link,
                callback_url=None,
                callback_method=None,
                callback_status=None,
                callback_response=None,
                delivered=True
            )
            session.add(transaction)
            
            await session.commit()
            
            async def handle_earning_task():
                try:
                    await process_premium_link_earning(
                        subscription_id=subscription.id,
                        publisher_id=file_record.publisher_id,
                        android_id=android_id,
                        hash_id=hash_id,
                        plan_id=subscription.plan_id
                    )
                except Exception as e:
                    logger.exception(f"Error in premium earning background task: {e}")
            
            asyncio.create_task(handle_earning_task())
            
            try:
                location = await get_request_location()
                country = location['country_name']
                country_code = location['country_code']
                region = location['region']
            except Exception as e:
                logger.error(f"Error getting location in /api/request: {e}")
                country = 'Unknown'
                country_code = 'Unknown'
                region = 'Unknown'
            
            return jsonify({
                'status': 'success',
                'message': 'Links generated successfully (subscription active)',
                'stream_link': stream_link,
                'download_link': download_link,
                'file_type': file_type,
                'country': country,
                'country_code': country_code,
                'region': region,
                'has_subscription': True
            }), 200
    
    # No subscription - return pending status (use postback)
    try:
        location = await get_request_location()
        country = location['country_name']
        country_code = location['country_code']
        region = location['region']
    except Exception as e:
        logger.error(f"Error getting location in /api/request: {e}")
        country = 'Unknown'
        country_code = 'Unknown'
        region = 'Unknown'
    
    logger.info(f"Non-subscribed user (android_id: {android_id}) requesting file {hash_id}. Returning pending status.")
    
    return jsonify({
        'status': 'pending',
        'message': 'Please wait, links are being generated. Use the postback URL to generate the links.',
        'country': country,
        'country_code': country_code,
        'region': region,
        'has_subscription': False
    }), 202

@bp.route('/api/postback', methods=['GET', 'POST'])
@require_endpoint_api_key('API Postback')
async def postback_generate_links():
    if request.method == 'GET':
        android_id = request.args.get('android_id', '').strip()
        hash_id = request.args.get('hash_id', '').strip()
        callback_url = request.args.get('callback_url', '').strip()
        callback_method = request.args.get('callback_method', '').strip()
    else:
        data = await request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400
        android_id = data.get('android_id', '').strip()
        hash_id = data.get('hash_id', '').strip()
        callback_url = data.get('callback_url', '').strip()
        callback_method = data.get('callback_method', '').strip()
    
    if not android_id or not hash_id:
        return jsonify({'status': 'error', 'message': 'android_id and hash_id are required'}), 400
    
    if not re.match(r'^[a-fA-F0-9]{24}$', hash_id):
        return jsonify({'status': 'error', 'message': 'Invalid hash_id format'}), 400
    
    # Validate callback URL to prevent SSRF attacks
    if callback_url:
        from bot.server.security import validate_callback_url
        is_valid, error_msg = validate_callback_url(callback_url)
        if not is_valid:
            return jsonify({'status': 'error', 'message': f'Invalid callback URL: {error_msg}'}), 400
    
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(File).where(File.access_code == hash_id)
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return jsonify({'status': 'error', 'message': 'File not found'}), 404
            
            if not file_record.is_active:
                return jsonify({'status': 'error', 'message': 'File has been revoked'}), 403
            
            settings_result = await session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            
            default_callback_mode = settings.callback_mode if settings and settings.callback_mode else 'POST'
            final_callback_method = callback_method if callback_method else default_callback_mode
            
            # Delete any existing links for the same android_id and hash_id combination
            delete_stmt = delete(DeviceLink).where(
                DeviceLink.android_id == android_id,
                DeviceLink.hash_id == hash_id
            )
            await session.execute(delete_stmt)
            logger.info(f"Deleted old links for android_id: {android_id}, hash_id: {hash_id}")
            
            stream_token = token_hex(32)
            download_token = token_hex(32)
            
            if file_record.video_duration and 0 < file_record.video_duration <= MAX_VIDEO_DURATION:
                expiry_seconds = file_record.video_duration + 3600
            else:
                expiry_seconds = 7200
            
            expiry_time = datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds)
            
            device_link = DeviceLink(
                file_id=file_record.telegram_message_id,
                android_id=android_id,
                hash_id=hash_id,
                stream_token=stream_token,
                download_token=download_token,
                link_expiry_time=expiry_time
            )
            session.add(device_link)
            
            file_type = detect_file_type(file_record.mime_type, file_record.filename)
            
            # Check if R2 is enabled and we have an object key for this file
            from bot.modules.r2_storage import get_r2_download_url
            r2_url = await get_r2_download_url(file_record.r2_object_key, expires_in=expiry_seconds)
            
            # Priority 1: External API Link Generation (TeraBox specific)
            if Server.EXTERNAL_LINK_GEN_URL:
                try:
                    logger.info(f"Using external API for link generation: {Server.EXTERNAL_LINK_GEN_URL}")
                    
                    # Extract TeraBox URL
                    terabox_url = getattr(file_record, 'terabox_url', None) or (file_record.custom_description if file_record.custom_description and 'terabox' in file_record.custom_description.lower() else None)
                    
                    if terabox_url:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            # Use the specific format provided by the user
                            # API: http://.../api/process?url=...
                            ext_response = await client.get(Server.EXTERNAL_LINK_GEN_URL, params={'url': terabox_url})
                            
                            if ext_response.status_code == 200:
                                ext_data = ext_response.json()
                                # The API returns proxy URLs starting with /
                                # We need to prepend the API base domain to these relative paths
                                from urllib.parse import urlparse
                                parsed_url = urlparse(Server.EXTERNAL_LINK_GEN_URL)
                                api_base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                                
                                stream_rel = ext_data.get('proxy_stream_url')
                                download_rel = ext_data.get('proxy_download_url')
                                
                                if stream_rel and download_rel:
                                    stream_link = f"{api_base}{stream_rel}"
                                    download_link = f"{api_base}{download_rel}"
                                    logger.info(f"Successfully fetched TeraBox links from external API for {hash_id}")
                                else:
                                    logger.warning(f"External API returned success but missing relative paths for {hash_id}")
                                    # Fallback logic...
                                    r2_url = await get_r2_download_url(file_record.r2_object_key, expires_in=expiry_seconds)
                                    if r2_url:
                                        stream_link = r2_url
                                        download_link = r2_url
                                    else:
                                        stream_link = f'{Server.BASE_URL}/stream/{file_record.telegram_message_id}?token={stream_token}'
                                        download_link = f'{Server.BASE_URL}/dl/{file_record.telegram_message_id}?token={download_token}&file_type={file_type}'
                            else:
                                logger.error(f"External API failed with status {ext_response.status_code}")
                                # Fallback logic...
                                r2_url = await get_r2_download_url(file_record.r2_object_key, expires_in=expiry_seconds)
                                if r2_url:
                                    stream_link = r2_url
                                    download_link = r2_url
                                else:
                                    stream_link = f'{Server.BASE_URL}/stream/{file_record.telegram_message_id}?token={stream_token}'
                                    download_link = f'{Server.BASE_URL}/dl/{file_record.telegram_message_id}?token={download_token}&file_type={file_type}'
                    else:
                        logger.warning(f"No TeraBox URL found for file {hash_id}, skipping external API")
                        # Fallback logic...
                        r2_url = await get_r2_download_url(file_record.r2_object_key, expires_in=expiry_seconds)
                        if r2_url:
                            stream_link = r2_url
                            download_link = r2_url
                        else:
                            stream_link = f'{Server.BASE_URL}/stream/{file_record.telegram_message_id}?token={stream_token}'
                            download_link = f'{Server.BASE_URL}/dl/{file_record.telegram_message_id}?token={download_token}&file_type={file_type}'
                except Exception as e:
                    logger.error(f"Error calling external link generation API: {e}")
                    # Fallback logic...
                    r2_url = await get_r2_download_url(file_record.r2_object_key, expires_in=expiry_seconds)
                    if r2_url:
                        stream_link = r2_url
                        download_link = r2_url
                    else:
                        stream_link = f'{Server.BASE_URL}/stream/{file_record.telegram_message_id}?token={stream_token}'
                        download_link = f'{Server.BASE_URL}/dl/{file_record.telegram_message_id}?token={download_token}&file_type={file_type}'
            
            # Priority 2: R2 URL if available (if no external API or it failed)
            elif r2_url:
                stream_link = r2_url
                download_link = r2_url
                logger.info(f"Serving R2 links for hash_id {hash_id} via postback")
            
            # Priority 3: Telegram internal links
            else:
                stream_link = f'{Server.BASE_URL}/stream/{file_record.telegram_message_id}?token={stream_token}'
                download_link = f'{Server.BASE_URL}/dl/{file_record.telegram_message_id}?token={download_token}&file_type={file_type}'
                logger.info(f"Serving Telegram links for hash_id {hash_id} via postback (R2 not available)")
            
            callback_status = None
            callback_response = None
            delivered = True
            
            if callback_url:
                success, status_code, response_text = await send_links_to_api(
                    android_id=android_id,
                    stream_link=stream_link,
                    download_link=download_link,
                    callback_url=callback_url,
                    callback_method=final_callback_method
                )
                callback_status = status_code
                callback_response = response_text
                delivered = success
            
            transaction = LinkTransaction(
                file_id=file_record.telegram_message_id,
                android_id=android_id,
                hash_id=hash_id,
                stream_link=stream_link,
                download_link=download_link,
                callback_url=callback_url,
                callback_method=final_callback_method if callback_url else None,
                callback_status=callback_status,
                callback_response=callback_response,
                delivered=delivered
            )
            session.add(transaction)
            
            await session.commit()
            
            logger.info(f"Links generated for android_id: {android_id}, hash_id: {hash_id}, callback: {callback_url}, method: {final_callback_method if callback_url else 'N/A'}")
            
            try:
                location = await get_request_location()
                country = location['country_name']
                country_code = location['country_code']
                region = location['region']
            except Exception as e:
                logger.error(f"Error getting location in /api/postback: {e}")
                country = 'Unknown'
                country_code = 'Unknown'
                region = 'Unknown'
            
            response_data = {
                'status': 'success',
                'message': 'Links generated successfully. Use /api/links endpoint to retrieve them.',
                'country': country,
                'country_code': country_code,
                'region': region
            }
            
            if callback_url and delivered:
                response_data['callback_delivered'] = True
            elif callback_url and not delivered:
                response_data['callback_delivered'] = False
                response_data['callback_error'] = callback_response
            
            return jsonify(response_data), 200
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error generating links: {e}")
            return jsonify({'status': 'error', 'message': 'Internal server error'}), 500

@bp.route('/api/links', methods=['POST'])
@api_rate_limit
@require_endpoint_api_key('API Links')
async def get_links_by_android_id():
    data = await request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400
    android_id = data.get('android_id', '').strip()
    hash_id = data.get('hash_id', '').strip()
    
    if not android_id or not hash_id:
        return jsonify({'status': 'error', 'message': 'android_id and hash_id are required'}), 400
    
    if not re.match(r'^[a-fA-F0-9]{24}$', hash_id):
        return jsonify({'status': 'error', 'message': 'Invalid hash_id format'}), 400
    
    async with AsyncSessionLocal() as session:
        file_result = await session.execute(
            select(File).where(File.access_code == hash_id)
        )
        file_record = file_result.scalar_one_or_none()
        
        if not file_record:
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        
        if not file_record.is_active:
            return jsonify({'status': 'error', 'message': 'File has been revoked'}), 403
        
        device_link_result = await session.execute(
            select(DeviceLink).where(
                DeviceLink.android_id == android_id,
                DeviceLink.hash_id == hash_id
            ).order_by(DeviceLink.created_at.desc())
        )
        device_link = device_link_result.scalar_one_or_none()
        
        if not device_link:
            return jsonify({'status': 'error', 'message': 'No links have been generated yet. Call /api/postback first.'}), 404
        
        if datetime.now(timezone.utc) > device_link.link_expiry_time:
            return jsonify({'status': 'error', 'message': 'Links have expired'}), 403
        
        file_type = detect_file_type(file_record.mime_type, file_record.filename)
        
        # Check if R2 is enabled and we have an object key for this file
        from bot.modules.r2_storage import get_r2_download_url
        r2_url = await get_r2_download_url(file_record.r2_object_key)
        
        # Priority: R2 URL if available, otherwise fallback to Telegram internal links
        if r2_url:
            stream_mobile_link = r2_url
            download_link = r2_url
            logger.info(f"Serving R2 links for hash_id {hash_id} in /api/links")
        else:
            stream_mobile_link = f'{Server.BASE_URL}/stream/mobile/{file_record.telegram_message_id}?token={device_link.stream_token}'
            download_link = f'{Server.BASE_URL}/dl/{file_record.telegram_message_id}?token={device_link.download_token}&file_type={file_type}'
            logger.info(f"Serving Telegram links for hash_id {hash_id} in /api/links (R2 not available)")
        
        # Generate thumbnail link if available
        thumbnail_link = None
        if file_record.thumbnail_file_id:
            thumbnail_link = f'{Server.BASE_URL}/thumbnail/{file_record.telegram_message_id}?token={device_link.stream_token}'
        
        location = await get_request_location()
        
        return jsonify({
            'status': 'success',
            'android_id': android_id,
            'hash_id': hash_id,
            'file_type': file_type,
            'filename': file_record.filename,
            'duration': file_record.video_duration,
            'thumbnail_link': thumbnail_link,
            'stream_mobile_link': stream_mobile_link,
            'download_link': download_link,
            'expires_at': device_link.link_expiry_time.isoformat(),
            'country': location['country_name'],
            'country_code': location['country_code'],
            'region': location['region']
        }), 200

@bp.route('/api/tracking/postback', methods=['GET'])
@require_endpoint_api_key('API Tracking Postback')
async def tracking_postback():
    hash_id = request.args.get('hash_id', '').strip()
    android_id = request.args.get('android_id', '').strip()
    
    if not hash_id or not android_id:
        return jsonify({
            'status': 'error',
            'message': 'hash_id and android_id are required'
        }), 400
    
    if not re.match(r'^[a-fA-F0-9]{24}$', hash_id):
        return jsonify({
            'status': 'error',
            'message': 'Invalid hash_id format'
        }), 400
    
    user_ip = request.remote_addr or request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or '0.0.0.0'
    
    location = await get_request_location()
    country_code = location['country_code']
    country_name = location['country_name']
    region = location['region']
    
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(File).where(File.access_code == hash_id)
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return jsonify({
                    'status': 'error',
                    'message': 'Video not found'
                }), 404
            
            if not file_record.is_active:
                return jsonify({
                    'status': 'error',
                    'message': 'File has been revoked'
                }), 403
            
            if not file_record.publisher_id:
                return jsonify({
                    'status': 'error',
                    'message': 'No publisher associated with this video'
                }), 400
            
            settings_result = await session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            
            if settings and settings.ipqs_enabled:
                key_id, api_key = await get_available_ipqs_key()
                
                if api_key:
                    user_agent = request.headers.get('User-Agent', '')
                    ipqs_result = await verify_ip_quality(api_key, user_ip, user_agent)
                    
                    if ipqs_result.success:
                        await increment_ipqs_key_usage(key_id)
                        
                        if not ipqs_result.is_valid_impression:
                            rejection_reason = ipqs_result.rejection_reason or "Invalid impression"
                            logger.info(f"IPQS rejected impression for IP {user_ip}: {rejection_reason}")
                            return jsonify({
                                'status': 'rejected',
                                'message': 'Impression not valid',
                                'reason': rejection_reason,
                                'fraud_score': ipqs_result.fraud_score
                            }), 200
                else:
                    logger.warning("IPQS enabled but no API keys available or all exhausted")
            
            cutback_percentage = settings.impression_cutback_percentage if settings else 0.0
            
            import random
            if cutback_percentage > 0 and random.uniform(0, 100) < cutback_percentage:
                logger.info(f"Impression cutback applied for hash_id: {hash_id}, cutback: {cutback_percentage}%")
                return jsonify({
                    'status': 'success',
                    'message': 'Request received but not tracked due to cutback',
                    'cutback': True,
                    'cutback_percentage': cutback_percentage
                }), 200
            
            impression_rate = 0.0
            
            publisher_result = await session.execute(
                select(Publisher).where(Publisher.id == file_record.publisher_id)
            )
            publisher = publisher_result.scalar_one_or_none()
            
            if publisher and publisher.custom_impression_rate is not None:
                impression_rate = publisher.custom_impression_rate
                logger.info(f"Using custom publisher rate for publisher {publisher.id}: ${impression_rate} per 1k impressions")
            elif country_code:
                country_rate_result = await session.execute(
                    select(CountryRate).where(
                        CountryRate.country_code == country_code,
                        CountryRate.is_active == True
                    )
                )
                country_rate = country_rate_result.scalar_one_or_none()
                
                if country_rate:
                    impression_rate = country_rate.impression_rate
                    logger.info(f"Using country-specific rate for {country_code}: ${impression_rate}")
            
            if impression_rate == 0.0:
                impression_rate = settings.impression_rate if settings else 0.0
                logger.info(f"Using default impression rate: ${impression_rate}")
            
            # Check for duplicate impression (same android_id + hash_id today)
            from datetime import date as date_type
            from sqlalchemy import func as sql_func
            today = date_type.today()
            
            duplicate_check = await session.execute(
                select(PublisherImpression).where(
                    PublisherImpression.android_id == android_id,
                    PublisherImpression.hash_id == hash_id,
                    sql_func.date(PublisherImpression.created_at) == today
                )
            )
            existing_impression = duplicate_check.scalar_one_or_none()
            
            if existing_impression:
                logger.info(f"Duplicate impression prevented for android_id: {android_id}, hash_id: {hash_id} (already tracked today)")
                return jsonify({
                    'status': 'success',
                    'message': 'Impression already tracked today',
                    'duplicate': True,
                    'publisher_id': file_record.publisher_id,
                    'hash_id': hash_id
                }), 200
            
            impression = PublisherImpression(
                publisher_id=file_record.publisher_id,
                hash_id=hash_id,
                android_id=android_id,
                user_ip=user_ip,
                country_code=country_code,
                country_name=country_name,
                region=region
            )
            session.add(impression)
            
            if publisher:
                publisher.balance += impression_rate
            
            await session.commit()
            
            logger.info(f"Impression tracked for publisher {file_record.publisher_id}, hash_id: {hash_id}, android_id: {android_id}, country: {country_code}, earned: ${impression_rate}")
            
            return jsonify({
                'status': 'success',
                'message': 'Impression tracked successfully',
                'publisher_id': file_record.publisher_id,
                'hash_id': hash_id,
                'country': country_name,
                'country_code': country_code,
                'region': region,
                'impression_rate': impression_rate
            }), 200
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error tracking impression: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Internal server error'
            }), 500

@bp.route('/api/video/description', methods=['GET'])
@require_endpoint_api_key('API Video Description')
async def get_video_description():
    hash_id = request.args.get('hash_id', '').strip()
    
    if not hash_id:
        return jsonify({
            'status': 'error',
            'message': 'hash_id is required'
        }), 400
    
    if not re.match(r'^[a-fA-F0-9]{24}$', hash_id):
        return jsonify({
            'status': 'error',
            'message': 'Invalid hash_id format'
        }), 400
    
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(File).where(File.access_code == hash_id)
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return jsonify({
                    'status': 'error',
                    'message': 'Video not found'
                }), 404
            
            if not file_record.is_active:
                return jsonify({
                    'status': 'error',
                    'message': 'Video is not active'
                }), 404
            
            description = file_record.custom_description
            
            if not description and file_record.publisher_id:
                publisher_result = await session.execute(
                    select(Publisher).where(Publisher.id == file_record.publisher_id)
                )
                publisher = publisher_result.scalar_one_or_none()
                
                if publisher and publisher.default_video_description:
                    description = publisher.default_video_description
            
            # Normalize line breaks: convert \r\n to \n
            if description:
                description = description.replace('\r\n', '\n').replace('\r', '\n')
            
            return jsonify({
                'status': 'success',
                'hash_id': hash_id,
                'filename': file_record.filename,
                'description': description or '',
                'has_custom_description': bool(file_record.custom_description),
                'has_default_description': bool(not file_record.custom_description and description)
            }), 200
            
        except Exception as e:
            logger.error(f"Error fetching video description: {e}")
            return jsonify({
                'status': 'error',
                'message': 'Internal server error'
            }), 500

@bp.route('/dl/<int:file_id>')
async def transmit_file(file_id):
    user_ip = request.remote_addr or request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or '0.0.0.0'
    user_agent = request.headers.get('User-Agent')
    
    file = await get_message(message_id=int(file_id))
    if not file:
        await log_access_attempt(file_id, user_ip or '', user_agent or '', False)
        abort(404)
    
    token = request.args.get('token')
    
    if not token:
        await log_access_attempt(file_id, user_ip or '', user_agent or '', False)
        abort(401, 'Token is required')
    
    async with AsyncSessionLocal() as session:
        file_result = await session.execute(
            select(File).where(File.telegram_message_id == file_id)
        )
        file_record = file_result.scalar_one_or_none()
        
        if not file_record:
            await log_access_attempt(file_id, user_ip or '', user_agent or '', False)
            abort(404)
        
        assert file_record is not None  # Type guard for LSP
        if not file_record.is_active:
            await log_access_attempt(file_id, user_ip or '', user_agent or '', False)
            abort(403, 'File has been revoked')
        
        device_link_result = await session.execute(
            select(DeviceLink).where(DeviceLink.download_token == token)
        )
        device_link = device_link_result.scalar_one_or_none()
        
        if not device_link or device_link.file_id != file_id:
            await log_access_attempt(file_id, user_ip or '', user_agent or '', False)
            abort(403, 'Invalid token')
        
        assert device_link is not None  # Type guard for LSP
        if datetime.now(timezone.utc) > device_link.link_expiry_time:
            await log_access_attempt(file_id, user_ip or '', user_agent or '', False)
            abort(403, 'Link has expired')
        
    range_header = request.headers.get('Range')
    
    # Log successful access attempt
    await log_access_attempt(file_id, user_ip or '', user_agent or '', True)

    assert file is not None  # Type guard for LSP
    file_name, file_size, mime_type = get_file_properties(file)
    
    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = 0
        until_bytes = file_size - 1

    if (until_bytes > file_size) or (from_bytes < 0) or (until_bytes < from_bytes):
        abort(416, 'Invalid range.')

    chunk_size = 1024 * 1024
    until_bytes = min(until_bytes, file_size - 1)

    offset = from_bytes - (from_bytes % chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = until_bytes % chunk_size + 1

    req_length = until_bytes - from_bytes + 1
    part_count = ceil(until_bytes / chunk_size) - floor(offset / chunk_size)
    
    headers = {
            "Content-Type": f"{mime_type}",
            "Content-Range": f"bytes {from_bytes}-{until_bytes}/{file_size}",
            "Content-Length": str(req_length),
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Accept-Ranges": "bytes",
        }

    async def file_generator():
        current_part = 1
        # Type hint to help LSP understand that file is valid for iter_download
        async for chunk in TelegramBot.iter_download(file, offset=offset, chunk_size=chunk_size, stride=chunk_size, file_size=file_size):  # type: ignore
            if not chunk:
                break
            elif part_count == 1:
                yield chunk[first_part_cut:last_part_cut]
            elif current_part == 1:
                yield chunk[first_part_cut:]
            elif current_part == part_count:
                yield chunk[:last_part_cut]
            else:
                yield chunk

            current_part += 1

            if current_part > part_count:
                break

    return Response(file_generator(), headers=headers, status=206 if range_header else 200)

@bp.route('/stream/<int:file_id>')
async def stream_file(file_id):
    token = request.args.get('token')
    
    if not token:
        abort(401, 'Token is required')
    
    async with AsyncSessionLocal() as session:
        file_result = await session.execute(
            select(File).where(File.telegram_message_id == file_id)
        )
        file_record = file_result.scalar_one_or_none()
        
        if not file_record:
            abort(404)
        
        assert file_record is not None  # Type guard for LSP
        if not file_record.is_active:
            abort(403, 'File has been revoked')
        
        device_link_result = await session.execute(
            select(DeviceLink).where(DeviceLink.stream_token == token)
        )
        device_link = device_link_result.scalar_one_or_none()
        
        if not device_link or device_link.file_id != file_id:
            abort(403, 'Invalid token')
        
        assert device_link is not None  # Type guard for LSP
        if datetime.now(timezone.utc) > device_link.link_expiry_time:
            abort(403, 'Link has expired')
        
        download_token = device_link.download_token
    
    return await render_template('player.html', mediaLink=f'{Server.BASE_URL}/dl/{file_id}?token={download_token}')

@bp.route('/stream/mobile/<int:file_id>')
async def stream_file_mobile(file_id):
    token = request.args.get('token')
    
    if not token:
        abort(401, 'Token is required')
    
    async with AsyncSessionLocal() as session:
        file_result = await session.execute(
            select(File).where(File.telegram_message_id == file_id)
        )
        file_record = file_result.scalar_one_or_none()
        
        if not file_record:
            abort(404)
        
        assert file_record is not None
        if not file_record.is_active:
            abort(403, 'File has been revoked')
        
        device_link_result = await session.execute(
            select(DeviceLink).where(DeviceLink.stream_token == token)
        )
        device_link = device_link_result.scalar_one_or_none()
        
        if not device_link or device_link.file_id != file_id:
            abort(403, 'Invalid token')
        
        assert device_link is not None
        if datetime.now(timezone.utc) > device_link.link_expiry_time:
            abort(403, 'Link has expired')
        
        download_token = device_link.download_token
    
    return await render_template('player_mobile.html', mediaLink=f'{Server.BASE_URL}/dl/{file_id}?token={download_token}')

@bp.route('/thumbnail/<int:file_id>')
async def get_thumbnail(file_id):
    token = request.args.get('token')
    
    if not token:
        abort(401, 'Token is required')
    
    async with AsyncSessionLocal() as session:
        file_result = await session.execute(
            select(File).where(File.telegram_message_id == file_id)
        )
        file_record = file_result.scalar_one_or_none()
        
        if not file_record:
            abort(404)
        
        assert file_record is not None
        if not file_record.is_active:
            abort(403, 'File has been revoked')
        
        if not file_record.thumbnail_file_id:
            abort(404, 'No thumbnail available for this file')
        
        device_link_result = await session.execute(
            select(DeviceLink).where(DeviceLink.stream_token == token)
        )
        device_link = device_link_result.scalar_one_or_none()
        
        if not device_link or device_link.file_id != file_id:
            abort(403, 'Invalid token')
        
        assert device_link is not None
        if datetime.now(timezone.utc) > device_link.link_expiry_time:
            abort(403, 'Link has expired')
    
    # Try to download thumbnail
    try:
        # Priority 1: Publisher's approved custom thumbnail (static file)
        if file_record.publisher_id:
            async with AsyncSessionLocal() as session:
                publisher_result = await session.execute(
                    select(Publisher).where(Publisher.id == file_record.publisher_id)
                )
                publisher = publisher_result.scalar_one_or_none()
                
                if publisher and publisher.thumbnail_approved and publisher.thumbnail_path:
                    thumbnail_path = Path(publisher.thumbnail_path)
                    if thumbnail_path.exists():
                        with open(thumbnail_path, 'rb') as f:
                            thumbnail_bytes = f.read()
                        
                        # Determine content type based on file extension
                        content_type = 'image/jpeg'
                        if thumbnail_path.suffix.lower() in ['.png']:
                            content_type = 'image/png'
                        elif thumbnail_path.suffix.lower() in ['.webp']:
                            content_type = 'image/webp'
                        elif thumbnail_path.suffix.lower() in ['.gif']:
                            content_type = 'image/gif'
                        
                        return Response(
                            thumbnail_bytes,
                            headers={
                                'Content-Type': content_type,
                                'Cache-Control': 'public, max-age=86400',
                                'Access-Control-Allow-Origin': '*'
                            },
                            status=200
                        )
        
        # Priority 2: Custom generated thumbnail uploaded to Telegram
        # Download thumbnail directly using the saved file_id (which is the message ID)
        if file_record.thumbnail_file_id:
            try:
                # Try to get the thumbnail message by its ID
                thumbnail_msg_id = int(file_record.thumbnail_file_id)
                thumbnail_msg = await TelegramBot.get_messages(Telegram.CHANNEL_ID, ids=thumbnail_msg_id)
                
                if thumbnail_msg and thumbnail_msg.photo:
                    thumbnail_bytes = await thumbnail_msg.download_media(bytes)
                    
                    if thumbnail_bytes:
                        logger.info(f"Serving custom generated thumbnail for file {file_id} using message ID {thumbnail_msg_id}")
                        return Response(
                            thumbnail_bytes,
                            headers={
                                'Content-Type': 'image/jpeg',
                                'Cache-Control': 'public, max-age=86400',
                                'Access-Control-Allow-Origin': '*'
                            },
                            status=200
                        )
            except Exception as thumb_err:
                logger.warning(f"Could not retrieve custom generated thumbnail using message ID: {thumb_err}")
                
                # Fallback: Search for thumbnail message using tracking caption
                try:
                    logger.info(f"Searching for thumbnail via caption for access_code: {file_record.access_code}")
                    async for message in TelegramBot.iter_messages(Telegram.CHANNEL_ID, limit=200):
                        if message.photo and message.text and f'THUMB_{file_record.access_code}' in message.text:
                            # Found the custom generated thumbnail message
                            thumbnail_bytes = await message.download_media(bytes)
                            if thumbnail_bytes:
                                logger.info(f"Serving custom generated thumbnail for file {file_id} (found via caption search)")
                                return Response(
                                    thumbnail_bytes,
                                    headers={
                                        'Content-Type': 'image/jpeg',
                                        'Cache-Control': 'public, max-age=86400',
                                        'Access-Control-Allow-Origin': '*'
                                    },
                                    status=200
                                )
                            break
                except Exception as search_err:
                    logger.warning(f"Could not retrieve custom generated thumbnail via caption search: {search_err}")
        
        # Priority 3: Fallback to original Telegram video thumbnail
        msg = await get_message(message_id=file_id)
        if msg and hasattr(msg, 'video') and msg.video:
            # Download thumbnail from the video
            thumbnail_bytes = await msg.download_media(bytes, thumb=-1)
            if thumbnail_bytes:
                logger.info(f"Serving original video thumbnail for file {file_id}")
                return Response(
                    thumbnail_bytes,
                    headers={
                        'Content-Type': 'image/jpeg',
                        'Cache-Control': 'public, max-age=86400',
                        'Access-Control-Allow-Origin': '*'
                    },
                    status=200
                )
        
        abort(404, 'Thumbnail not available')
        
    except Exception as e:
        logger.error(f"Error downloading thumbnail: {e}")
        abort(500, 'Failed to download thumbnail')

@bp.route('/play/<hash_id>')
async def play_video(hash_id):
    async with AsyncSessionLocal() as session:
        file_result = await session.execute(
            select(File).where(File.access_code == hash_id)
        )
        file_record = file_result.scalar_one_or_none()
        
        if not file_record:
            abort(404, 'File not found')
        
        assert file_record is not None  # Type guard for LSP
        if not file_record.is_active:
            abort(403, 'This file has been removed')
        
        settings_result = await session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        
        package_name = settings.android_package_name if settings and settings.android_package_name else ''
        deep_link_scheme = settings.android_deep_link_scheme if settings and settings.android_deep_link_scheme else ''
        filename = file_record.filename
        
        file_type = detect_file_type(file_record.mime_type, file_record.filename)
    
    template_map = {
        'apk': 'play_apk.html',
        'zip': 'play_zip.html',
        'video': 'play.html'
    }
    
    template_name = template_map.get(file_type, 'play.html')
    
    return await render_template(template_name, 
                                hash_id=hash_id, 
                                package_name=package_name, 
                                deep_link_scheme=deep_link_scheme,
                                filename=filename)

@bp.route('/payment-link')
async def payment_link():
    order_id = request.args.get('order_id')
    
    if not order_id:
        abort(400, 'Order ID is required')
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.order_id == order_id)
        )
        subscription = result.scalar_one_or_none()
        
        if not subscription:
            abort(404, 'Payment not found')
        
        assert subscription is not None  # Type guard for LSP
        
        settings_result = await session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        
        upi_id = settings.paytm_upi_id if settings and settings.paytm_upi_id else os.environ.get('PAYTM_UPI_ID', '')
        payee_name = settings.paytm_unit_id if settings and settings.paytm_unit_id else os.environ.get('PAYTM_UNIT_ID', '')
        paytm_signature = settings.paytm_signature if settings and settings.paytm_signature else os.environ.get('PAYTM_SIGNATURE', '')
        
        import urllib.parse
        upi_link = f"upi://pay?pa={upi_id}&am={subscription.amount}&pn={payee_name}&tn={order_id}&tr={order_id}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&ecc=H&margin=20&data={urllib.parse.quote(upi_link)}"
        
        if paytm_signature:
            paytm_intent = f"paytmmp://cash_wallet?pa={upi_id}&pn={payee_name}&am={subscription.amount}&cu=INR&tn={order_id}&tr={order_id}&mc=4722&sign={paytm_signature}&featuretype=money_transfer"
        else:
            paytm_intent = f"paytmmp://cash_wallet?pa={upi_id}&pn={payee_name}&am={subscription.amount}&cu=INR&tn={order_id}&tr={order_id}&mc=4722&featuretype=money_transfer"
        
        created_at = subscription.created_at.isoformat() if subscription.created_at else datetime.utcnow().isoformat()
        
        return await render_template('payment_link.html',
                                    order_id=order_id,
                                    amount=subscription.amount,
                                    plan_name=subscription.plan_name,
                                    qr_url=qr_url,
                                    paytm_intent=paytm_intent,
                                    upi_link=upi_link,
                                    created_at=created_at)

@bp.route('/terms-of-service')
async def terms_of_service():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Settings))
        settings = result.scalar_one_or_none()
        
        terms = settings.terms_of_service if settings else 'Terms of Service not available.'
    
    return await render_template('terms.html', content=terms, title='Terms of Service')

@bp.route('/privacy-policy')
async def privacy_policy():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Settings))
        settings = result.scalar_one_or_none()
        
        privacy = settings.privacy_policy if settings else 'Privacy Policy not available.'
    
    return await render_template('privacy.html', content=privacy, title='Privacy Policy')