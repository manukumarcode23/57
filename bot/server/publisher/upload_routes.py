from quart import Blueprint, request, render_template, session, jsonify
from bot.database import AsyncSessionLocal
from bot.models import File, Publisher, Settings
from bot.server.publisher.utils import require_publisher
from bot.server.security import csrf_protect, get_csrf_token, rate_limit
from bot import TelegramBot
from bot.config import Telegram, Server
from bot.modules.telegram import get_message, get_file_properties
from bot.modules.file_validator import validate_file_type, sanitize_filename
from bot.server.publisher.subscription_routes import check_upload_allowed
from sqlalchemy import select
from secrets import token_hex
import os
import tempfile
from werkzeug.utils import secure_filename
import logging

from bot.database import generate_unique_access_code
from bot.modules.r2_storage import upload_file_to_r2

bp = Blueprint('publisher_upload', __name__)
logger = logging.getLogger('bot.server')

async def get_web_upload_limits():
    """Get web upload limits from settings"""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(Settings))
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

@bp.route('/upload')
@require_publisher
async def upload():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        publisher = result.scalar_one_or_none()
    
    csrf_token = get_csrf_token()
    return await render_template('publisher_upload.html', 
                                  active_page='upload',
                                  email=session['publisher_email'],
                                  traffic_source=publisher.traffic_source if publisher else '',
                                  api_key=publisher.api_key if publisher else None,
                                  csrf_token=csrf_token)

@bp.route('/upload-video', methods=['POST'])
@require_publisher
@csrf_protect
async def upload_video():
    temp_path = None
    active_subscription = None
    try:
        upload_allowed, active_subscription, subscription_message = await check_upload_allowed(session['publisher_id'])
        if not upload_allowed:
            return jsonify({
                'status': 'error',
                'message': subscription_message,
                'subscription_required': True
            }), 403
        
        limits = await get_web_upload_limits()
        
        # Enforce web upload rate limiting
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select, delete
        from bot.models import RateLimit
        
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
        
        original_filename = uploaded_file.filename
        safe_filename = secure_filename(sanitize_filename(original_filename)) or 'file_upload'
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'_{safe_filename}') as temp_file:
            temp_path = temp_file.name
        
        await uploaded_file.save(temp_path)
        
        # Use configurable web upload file size limit from database
        file_size = os.path.getsize(temp_path)
        if file_size > limits['max_file_size_bytes']:
            max_size_gb = limits['max_file_size_bytes'] / (1024 * 1024 * 1024)
            return jsonify({'status': 'error', 'message': f'File size exceeds {max_size_gb:.1f} GB limit'}), 400
        
        secret_code = await generate_unique_access_code()
        
        # Handle R2 upload if enabled
        r2_key = await upload_file_to_r2(temp_path, f"{secret_code}/{safe_filename}")
        
        async with AsyncSessionLocal() as db_session_thumb:
            result = await db_session_thumb.execute(
                select(Publisher).where(Publisher.id == session['publisher_id'])
            )
            publisher_for_thumb = result.scalar_one_or_none()
            
            thumbnail_path = None
            if publisher_for_thumb and publisher_for_thumb.thumbnail_path:
                thumbnail_path = f'bot/server/static/{publisher_for_thumb.thumbnail_path}'
                if not os.path.exists(thumbnail_path):
                    thumbnail_path = None
        
        send_kwargs = {
            'entity': Telegram.CHANNEL_ID,
            'file': temp_path,
            'caption': f'`{secret_code}`',
            'force_document': False,
            'attributes': None
        }
        
        sent_message = await TelegramBot.send_file(**send_kwargs)
        
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
        
        filename, file_size, mime_type = get_file_properties(telegram_message)
        
        video_duration = None
        if hasattr(telegram_message, 'video') and telegram_message.video:
            if hasattr(telegram_message.video, 'attributes'):
                for attr in telegram_message.video.attributes:
                    duration = getattr(attr, 'duration', None)
                    if duration:
                        video_duration = duration
                        break
        elif hasattr(telegram_message, 'document') and telegram_message.document:
            if hasattr(telegram_message.document, 'attributes'):
                for attr in telegram_message.document.attributes:
                    duration = getattr(attr, 'duration', None)
                    if duration:
                        video_duration = duration
                        break
        
        async with AsyncSessionLocal() as db_session:
            try:
                file_record = File(
                    telegram_message_id=message_id,
                    filename=filename,
                    file_size=file_size,
                    mime_type=mime_type,
                    access_code=secret_code,
                    video_duration=int(video_duration) if video_duration else None,
                    publisher_id=session.get('publisher_id'),
                    r2_object_key=r2_key
                )
                db_session.add(file_record)
                await db_session.commit()
            except Exception as e:
                await db_session.rollback()
                logger.error(f"Error saving file to database: {e}")
                return jsonify({'status': 'error', 'message': 'Database error'}), 500
        
        logger.info(f"File uploaded by publisher {session['publisher_email']}: {filename}, hash_id: {secret_code}")
        
        play_link = f'{Server.BASE_URL}/play/{secret_code}'
        
        return jsonify({
            'status': 'success',
            'hash_id': secret_code,
            'play_link': play_link,
            'filename': filename,
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
