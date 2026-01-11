from quart import Blueprint, request, render_template, redirect
from bot.database import AsyncSessionLocal
from bot.models import Bot
from sqlalchemy import select
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token

bp = Blueprint('admin_bots', __name__)

@bp.route('/bots')
@require_admin
async def bots():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Bot).order_by(Bot.created_at.desc())
        )
        bots = result.scalars().all()
        
    csrf_token = get_csrf_token()
    return await render_template('admin_bots.html', active_page='bots', bots=bots, csrf_token=csrf_token)

@bp.route('/bots/add', methods=['POST'])
@require_admin
@csrf_protect
async def add_bot():
    data = await request.form
    
    async with AsyncSessionLocal() as db_session:
        try:
            bot = Bot(
                bot_name=data.get('bot_name', '').strip(),
                bot_link=data.get('bot_link', '').strip(),
                purpose=data.get('purpose', '').strip(),
                is_active=data.get('is_active', 'on') == 'on'
            )
            
            db_session.add(bot)
            await db_session.commit()
            
            return redirect('/admin/bots')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/bots')

@bp.route('/bots/edit/<int:bot_id>', methods=['POST'])
@require_admin
@csrf_protect
async def edit_bot(bot_id):
    data = await request.form
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Bot).where(Bot.id == bot_id)
            )
            bot = result.scalar_one_or_none()
            
            if bot:
                bot.bot_name = data.get('bot_name', '').strip()
                bot.bot_link = data.get('bot_link', '').strip()
                bot.purpose = data.get('purpose', '').strip()
                bot.is_active = data.get('is_active', 'on') == 'on'
                
                await db_session.commit()
            
            return redirect('/admin/bots')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/bots')

@bp.route('/bots/toggle/<int:bot_id>', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_bot(bot_id):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Bot).where(Bot.id == bot_id)
            )
            bot = result.scalar_one_or_none()
            
            if bot:
                bot.is_active = not bot.is_active
                await db_session.commit()
            
            return redirect('/admin/bots')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/bots')

@bp.route('/bots/delete/<int:bot_id>', methods=['POST'])
@require_admin
@csrf_protect
async def delete_bot(bot_id):
    from sqlalchemy import delete
    async with AsyncSessionLocal() as db_session:
        try:
            # Use delete statement instead of session.delete
            stmt = delete(Bot).where(Bot.id == bot_id)
            await db_session.execute(stmt)
            await db_session.commit()
            
            return redirect('/admin/bots')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/bots')
