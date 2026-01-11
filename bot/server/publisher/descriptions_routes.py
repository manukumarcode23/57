from quart import Blueprint, render_template, request, session, jsonify
from bot.server.publisher.utils import require_publisher
from bot.server.security import csrf_protect
from bot.database import AsyncSessionLocal
from bot.models import Publisher, File
from sqlalchemy import select, and_
from logging import getLogger

logger = getLogger('bot.publisher.descriptions')

bp = Blueprint('publisher_descriptions', __name__)

@bp.route('/descriptions')
@require_publisher
async def descriptions():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        publisher = result.scalar_one_or_none()
        
        files_result = await db_session.execute(
            select(File).where(
                and_(
                    File.publisher_id == session['publisher_id'],
                    File.is_active == True
                )
            ).order_by(File.created_at.desc())
        )
        files = files_result.scalars().all()
        
        csrf_token = session.get('csrf_token')
        
        return await render_template('publisher_descriptions.html', 
                                    publisher=publisher,
                                    files=files,
                                    email=session.get('publisher_email'),
                                    active_page='descriptions',
                                    csrf_token=csrf_token)

@bp.route('/descriptions/update-default', methods=['POST'])
@require_publisher
@csrf_protect
async def update_default_description():
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

@bp.route('/descriptions/update-custom/<access_code>', methods=['POST'])
@require_publisher
@csrf_protect
async def update_custom_description(access_code):
    data = await request.form
    custom_description = data.get('custom_description', '').strip()
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(File).where(
                    and_(
                        File.access_code == access_code,
                        File.publisher_id == session['publisher_id']
                    )
                )
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return jsonify({'status': 'error', 'message': 'File not found or access denied'}), 404
            
            file_record.custom_description = custom_description if custom_description else None
            await db_session.commit()
            
            logger.info(f"Custom description updated for file {access_code} by publisher {session['publisher_email']}")
            
            return jsonify({'status': 'success', 'message': 'Custom description updated successfully'}), 200
        
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error updating custom description: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to update description'}), 500
