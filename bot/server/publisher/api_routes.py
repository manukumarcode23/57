from quart import Blueprint, render_template, session, jsonify, redirect
from bot.database import AsyncSessionLocal
from bot.models import Publisher, Bot
from bot.server.publisher.utils import require_publisher
from bot.server.security import csrf_protect, get_csrf_token
from sqlalchemy import select
from secrets import token_hex
import logging

bp = Blueprint('publisher_api', __name__)
logger = logging.getLogger('bot.server')

@bp.route('/api-management')
@require_publisher
async def api_management():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        publisher = result.scalar_one_or_none()
        
        if not publisher:
            return redirect('/login')
        
        bots_result = await db_session.execute(
            select(Bot).where(Bot.is_active == True).order_by(Bot.created_at.desc())
        )
        bots = bots_result.scalars().all()
    
    csrf_token = get_csrf_token()
    return await render_template('api_management.html', 
                                  active_page='api',
                                  email=session['publisher_email'],
                                  api_key=publisher.api_key,
                                  bots=bots,
                                  csrf_token=csrf_token)

@bp.route('/generate-api-key', methods=['POST'])
@require_publisher
@csrf_protect
async def generate_api_key():
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == session['publisher_id'])
            )
            publisher = result.scalar_one_or_none()
            
            if not publisher:
                return jsonify({'status': 'error', 'message': 'Publisher not found'}), 404
            
            new_api_key = token_hex(32)
            publisher.api_key = new_api_key
            publisher.telegram_id = None
            await db_session.commit()
            
            return jsonify({'status': 'success', 'api_key': new_api_key}), 200
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error generating API key: {e}")
            return jsonify({'status': 'error', 'message': 'Failed to generate API key'}), 500
