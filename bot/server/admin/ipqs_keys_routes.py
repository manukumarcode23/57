from quart import Blueprint, request, render_template, redirect
from bot.database import AsyncSessionLocal
from bot.models import IPQSApiKey, Settings
from sqlalchemy import select
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token
from datetime import datetime, timezone

bp = Blueprint('admin_ipqs_keys', __name__)


@bp.route('/ipqs-keys')
@require_admin
async def ipqs_keys():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(IPQSApiKey).order_by(IPQSApiKey.created_at.desc())
        )
        keys = result.scalars().all()
        
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        ipqs_enabled = settings.ipqs_enabled if settings else False
    
    csrf_token = get_csrf_token()
    return await render_template(
        'admin_ipqs_keys.html', 
        active_page='ipqs_keys', 
        keys=keys, 
        ipqs_enabled=ipqs_enabled,
        csrf_token=csrf_token
    )


@bp.route('/ipqs-keys/add', methods=['POST'])
@require_admin
@csrf_protect
async def add_ipqs_key():
    data = await request.form
    
    label = data.get('label', '').strip()
    api_key = data.get('api_key', '').strip()
    request_limit = data.get('request_limit', '1000').strip()
    
    if not label or not api_key:
        return redirect('/admin/ipqs-keys?error=Label and API Key are required')
    
    try:
        request_limit = int(request_limit)
        if request_limit < 1:
            request_limit = 1000
    except ValueError:
        request_limit = 1000
    
    async with AsyncSessionLocal() as db_session:
        try:
            new_key = IPQSApiKey(
                label=label,
                api_key=api_key,
                request_limit=request_limit,
                usage_count=0,
                is_active=True
            )
            db_session.add(new_key)
            await db_session.commit()
            return redirect('/admin/ipqs-keys?success=IPQS API key added successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect(f'/admin/ipqs-keys?error=Failed to add API key: {str(e)}')


@bp.route('/ipqs-keys/edit/<int:key_id>', methods=['POST'])
@require_admin
@csrf_protect
async def edit_ipqs_key(key_id: int):
    data = await request.form
    
    label = data.get('label', '').strip()
    api_key = data.get('api_key', '').strip()
    request_limit = data.get('request_limit', '1000').strip()
    
    if not label:
        return redirect('/admin/ipqs-keys?error=Label is required')
    
    try:
        request_limit = int(request_limit)
        if request_limit < 1:
            request_limit = 1000
    except ValueError:
        request_limit = 1000
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(IPQSApiKey).where(IPQSApiKey.id == key_id)
            )
            key = result.scalar_one_or_none()
            
            if not key:
                return redirect('/admin/ipqs-keys?error=API key not found')
            
            key.label = label
            key.request_limit = request_limit
            
            if api_key:
                key.api_key = api_key
            
            await db_session.commit()
            return redirect('/admin/ipqs-keys?success=API key updated successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect(f'/admin/ipqs-keys?error=Failed to update API key: {str(e)}')


@bp.route('/ipqs-keys/toggle/<int:key_id>', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_ipqs_key(key_id: int):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(IPQSApiKey).where(IPQSApiKey.id == key_id)
            )
            key = result.scalar_one_or_none()
            
            if not key:
                return redirect('/admin/ipqs-keys?error=API key not found')
            
            key.is_active = not key.is_active
            await db_session.commit()
            
            status = 'enabled' if key.is_active else 'disabled'
            return redirect(f'/admin/ipqs-keys?success=API key {status} successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/ipqs-keys?error=Failed to toggle API key status')


@bp.route('/ipqs-keys/reset/<int:key_id>', methods=['POST'])
@require_admin
@csrf_protect
async def reset_ipqs_key_usage(key_id: int):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(IPQSApiKey).where(IPQSApiKey.id == key_id)
            )
            key = result.scalar_one_or_none()
            
            if not key:
                return redirect('/admin/ipqs-keys?error=API key not found')
            
            key.usage_count = 0
            await db_session.commit()
            
            return redirect('/admin/ipqs-keys?success=Usage count reset successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/ipqs-keys?error=Failed to reset usage count')


@bp.route('/ipqs-keys/delete/<int:key_id>', methods=['POST'])
@require_admin
@csrf_protect
async def delete_ipqs_key(key_id: int):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(IPQSApiKey).where(IPQSApiKey.id == key_id)
            )
            key = result.scalar_one_or_none()
            
            if not key:
                return redirect('/admin/ipqs-keys?error=API key not found')
            
            await db_session.delete(key)
            await db_session.commit()
            
            return redirect('/admin/ipqs-keys?success=API key deleted successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/ipqs-keys?error=Failed to delete API key')


@bp.route('/ipqs-keys/toggle-global', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_ipqs_global():
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = Settings(ipqs_enabled=True)
                db_session.add(settings)
                await db_session.commit()
                return redirect('/admin/ipqs-keys?success=IPQS verification enabled globally')
            
            settings.ipqs_enabled = not settings.ipqs_enabled
            await db_session.commit()
            
            status = 'enabled' if settings.ipqs_enabled else 'disabled'
            return redirect(f'/admin/ipqs-keys?success=IPQS verification {status} globally')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/ipqs-keys?error=Failed to toggle IPQS status')
