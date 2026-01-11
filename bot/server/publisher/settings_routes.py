from quart import Blueprint, request, render_template, session, jsonify, redirect
from bot.database import AsyncSessionLocal
from bot.models import Publisher
from bot.server.publisher.utils import require_publisher
from bot.server.security import csrf_protect, get_csrf_token, is_strong_password
from sqlalchemy import select
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
from secrets import token_hex
from PIL import Image
import os
import logging

bp = Blueprint('publisher_settings', __name__)
logger = logging.getLogger('bot.server')

@bp.route('/settings')
@require_publisher
async def settings():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        publisher = result.scalar_one_or_none()
        
        if not publisher:
            return redirect('/login')
    
    csrf_token = get_csrf_token()
    return await render_template('publisher_settings.html',
                                  active_page='settings',
                                  email=session['publisher_email'],
                                  publisher=publisher,
                                  csrf_token=csrf_token)

@bp.route('/settings/update-password', methods=['POST'])
@require_publisher
@csrf_protect
async def update_password():
    data = await request.form
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not all([current_password, new_password, confirm_password]):
        return jsonify({'status': 'error', 'message': 'All fields are required'}), 400
    
    if new_password != confirm_password:
        return jsonify({'status': 'error', 'message': 'New passwords do not match'}), 400
    
    is_valid, password_error = is_strong_password(new_password)
    if not is_valid:
        return jsonify({'status': 'error', 'message': password_error}), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == session['publisher_id'])
            )
            publisher = result.scalar_one_or_none()
            
            if not publisher:
                return jsonify({'status': 'error', 'message': 'Publisher not found'}), 404
            
            if not check_password_hash(publisher.password_hash, current_password):
                return jsonify({'status': 'error', 'message': 'Current password is incorrect'}), 400
            
            publisher.password_hash = generate_password_hash(new_password)
            await db_session.commit()
            
            logger.info(f"Password updated for publisher {session['publisher_email']}")
            
            return jsonify({'status': 'success', 'message': 'Password updated successfully'}), 200
        
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error updating password: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to update password'}), 500

@bp.route('/settings/update-thumbnail', methods=['POST'])
@require_publisher
@csrf_protect
async def update_thumbnail():
    temp_path = None
    max_size = 5 * 1024 * 1024
    
    try:
        content_length = request.content_length
        if content_length and content_length > max_size:
            return jsonify({'status': 'error', 'message': 'File size exceeds 5 MB limit'}), 400
        
        files = await request.files
        if 'thumbnail' not in files:
            return jsonify({'status': 'error', 'message': 'No thumbnail provided'}), 400
        
        thumbnail_file = files['thumbnail']
        if not thumbnail_file.filename:
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400
        
        file_ext = Path(thumbnail_file.filename).suffix.lower()
        if file_ext not in ['.jpg', '.jpeg', '.png', '.webp']:
            return jsonify({'status': 'error', 'message': 'Invalid file type. Allowed: JPG, PNG, WebP'}), 400
        
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_path = temp_file.name
            
            total_size = 0
            chunk_size = 8192
            while True:
                chunk = thumbnail_file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    temp_file.close()
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                    return jsonify({'status': 'error', 'message': 'File size exceeds 5 MB limit'}), 400
                temp_file.write(chunk)
        
        file_size = os.path.getsize(temp_path)
        if file_size > max_size:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({'status': 'error', 'message': 'File size exceeds 5 MB limit'}), 400
        
        # Validate image dimensions and aspect ratio
        jpeg_temp_path = None
        try:
            with Image.open(temp_path) as img:
                width, height = img.size
                
                # Check for exact dimensions (1280x720)
                if width != 1280 or height != 720:
                    # Check if aspect ratio is exactly 16:9
                    aspect_ratio = width / height
                    target_ratio = 16 / 9
                    
                    # Allow small floating point tolerance
                    if abs(aspect_ratio - target_ratio) > 0.01:
                        if temp_path and os.path.exists(temp_path):
                            os.remove(temp_path)
                        return jsonify({
                            'status': 'error',
                            'message': 'Invalid image dimensions. Required: 1280x720 pixels (16:9 aspect ratio)',
                            'current_dimensions': f'{width}x{height}'
                        }), 400
                    
                    # If aspect ratio is correct but dimensions are not 1280x720, resize
                    img = img.resize((1280, 720), Image.Resampling.LANCZOS)
                    logger.info(f"Resized thumbnail from {width}x{height} to 1280x720")
                
                # Always convert to RGB
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Create a new temp file with .jpg extension and save as JPEG
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as jpeg_temp:
                    jpeg_temp_path = jpeg_temp.name
                    img.save(jpeg_temp_path, format='JPEG', quality=95)
                    logger.info(f"Converted thumbnail to JPEG format")
            
            # Remove the original temp file
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            
            # Use the JPEG temp file as the new temp path
            temp_path = jpeg_temp_path
            jpeg_temp_path = None
                    
        except Exception as e:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            if jpeg_temp_path and os.path.exists(jpeg_temp_path):
                os.remove(jpeg_temp_path)
            logger.error(f"Error validating thumbnail image: {e}")
            return jsonify({'status': 'error', 'message': 'Invalid image file or corrupted'}), 400
        
        thumbnails_dir = Path('bot/server/static/thumbnails')
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        
        # Always use .jpg extension for consistency
        filename = f'publisher_{session["publisher_id"]}_{token_hex(8)}.jpg'
        filepath = thumbnails_dir / filename
        
        import shutil
        shutil.move(temp_path, str(filepath))
        temp_path = None
        
        async with AsyncSessionLocal() as db_session:
            try:
                result = await db_session.execute(
                    select(Publisher).where(Publisher.id == session['publisher_id'])
                )
                publisher = result.scalar_one_or_none()
                
                if not publisher:
                    if os.path.exists(str(filepath)):
                        os.remove(str(filepath))
                    return jsonify({'status': 'error', 'message': 'Publisher not found'}), 404
                
                if publisher.thumbnail_path:
                    old_thumbnail = Path('bot/server/static') / publisher.thumbnail_path
                    if old_thumbnail.exists():
                        try:
                            os.remove(str(old_thumbnail))
                            logger.info(f"Removed old thumbnail: {publisher.thumbnail_path}")
                        except Exception as e:
                            logger.error(f"Could not remove old thumbnail {publisher.thumbnail_path}: {e}", exc_info=True)
                
                publisher.thumbnail_path = f'thumbnails/{filename}'
                publisher.thumbnail_approved = False
                publisher.thumbnail_status = 'pending'
                await db_session.commit()
                
                logger.info(f"Thumbnail uploaded for publisher {session['publisher_email']}, pending admin approval")
                
                return jsonify({
                    'status': 'success',
                    'message': 'Thumbnail uploaded successfully. Awaiting admin approval.',
                    'thumbnail_url': f'/static/thumbnails/{filename}',
                    'pending_approval': True
                }), 200
            
            except Exception as e:
                await db_session.rollback()
                if filepath.exists():
                    try:
                        os.remove(str(filepath))
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup file after DB error: {cleanup_error}")
                logger.error(f"Error updating thumbnail in database: {e}", exc_info=True)
                return jsonify({'status': 'error', 'message': 'Failed to update thumbnail'}), 500
    
    except Exception as e:
        logger.error(f"Thumbnail upload error: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Could not remove temp file {temp_path}: {e}")

@bp.route('/settings/delete-thumbnail', methods=['POST'])
@require_publisher
@csrf_protect
async def delete_thumbnail():
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == session['publisher_id'])
            )
            publisher = result.scalar_one_or_none()
            
            if not publisher:
                return jsonify({'status': 'error', 'message': 'Publisher not found'}), 404
            
            if publisher.thumbnail_path:
                old_thumbnail = Path('bot/server/static') / publisher.thumbnail_path
                if old_thumbnail.exists():
                    try:
                        os.remove(str(old_thumbnail))
                    except Exception as e:
                        logger.warning(f"Could not remove thumbnail file: {e}")
                
                publisher.thumbnail_path = None
                publisher.thumbnail_approved = False
                publisher.thumbnail_status = None
                await db_session.commit()
                
                logger.info(f"Thumbnail deleted for publisher {session['publisher_email']}")
            
            return jsonify({'status': 'success', 'message': 'Thumbnail deleted successfully'}), 200
        
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error deleting thumbnail: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to delete thumbnail'}), 500

@bp.route('/settings/update-logo', methods=['POST'])
@require_publisher
@csrf_protect
async def update_logo():
    temp_path = None
    max_size = 5 * 1024 * 1024
    
    try:
        content_length = request.content_length
        if content_length and content_length > max_size:
            return jsonify({'status': 'error', 'message': 'File size exceeds 5 MB limit'}), 400
        
        files = await request.files
        if 'logo' not in files:
            return jsonify({'status': 'error', 'message': 'No logo provided'}), 400
        
        logo_file = files['logo']
        if not logo_file.filename:
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400
        
        file_ext = Path(logo_file.filename).suffix.lower()
        if file_ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            return jsonify({'status': 'error', 'message': 'Invalid file type. Allowed: JPG, PNG, WebP, GIF'}), 400
        
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_path = temp_file.name
            
            total_size = 0
            chunk_size = 8192
            while True:
                chunk = logo_file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    temp_file.close()
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                    return jsonify({'status': 'error', 'message': 'File size exceeds 5 MB limit'}), 400
                temp_file.write(chunk)
        
        file_size = os.path.getsize(temp_path)
        if file_size > max_size:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return jsonify({'status': 'error', 'message': 'File size exceeds 5 MB limit'}), 400
        
        logos_dir = Path('bot/server/static/logos')
        logos_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f'publisher_{session["publisher_id"]}_{token_hex(8)}{file_ext}'
        filepath = logos_dir / filename
        
        import shutil
        shutil.move(temp_path, str(filepath))
        temp_path = None
        
        async with AsyncSessionLocal() as db_session:
            try:
                result = await db_session.execute(
                    select(Publisher).where(Publisher.id == session['publisher_id'])
                )
                publisher = result.scalar_one_or_none()
                
                if not publisher:
                    if os.path.exists(str(filepath)):
                        os.remove(str(filepath))
                    return jsonify({'status': 'error', 'message': 'Publisher not found'}), 404
                
                if publisher.logo_path:
                    old_logo = Path('bot/server/static') / publisher.logo_path
                    if old_logo.exists():
                        try:
                            os.remove(str(old_logo))
                            logger.info(f"Removed old logo: {publisher.logo_path}")
                        except Exception as e:
                            logger.error(f"Could not remove old logo {publisher.logo_path}: {e}", exc_info=True)
                
                publisher.logo_path = f'logos/{filename}'
                await db_session.commit()
                
                logger.info(f"Logo updated for publisher {session['publisher_email']}")
                
                return jsonify({
                    'status': 'success',
                    'message': 'Logo updated successfully',
                    'logo_url': f'/static/logos/{filename}'
                }), 200
            
            except Exception as e:
                await db_session.rollback()
                if filepath.exists():
                    try:
                        os.remove(str(filepath))
                    except Exception as cleanup_error:
                        logger.error(f"Failed to cleanup file after DB error: {cleanup_error}")
                logger.error(f"Error updating logo in database: {e}", exc_info=True)
                return jsonify({'status': 'error', 'message': 'Failed to update logo'}), 500
    
    except Exception as e:
        logger.error(f"Logo upload error: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                logger.warning(f"Could not remove temp file {temp_path}: {e}")

@bp.route('/settings/update-description', methods=['POST'])
@require_publisher
@csrf_protect
async def update_description():
    data = await request.form
    default_description = data.get('default_description', '').strip()
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == session['publisher_id'])
            )
            publisher = result.scalar_one_or_none()
            
            if not publisher:
                return jsonify({'status': 'error', 'message': 'Publisher not found'}), 404
            
            publisher.default_video_description = default_description if default_description else None
            await db_session.commit()
            
            logger.info(f"Default video description updated for publisher {session['publisher_email']}")
            
            return jsonify({'status': 'success', 'message': 'Default description updated successfully'}), 200
        
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error updating default description: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to update description'}), 500
