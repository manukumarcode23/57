from quart import Blueprint, request, render_template, redirect, jsonify
from bot.database import AsyncSessionLocal
from bot.models import CloudflareR2Settings, Settings
from sqlalchemy import select
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token

bp = Blueprint('admin_r2_keys', __name__)

@bp.route('/r2-storage')
@require_admin
async def r2_storage():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(CloudflareR2Settings))
        r2_settings = result.scalars().all()
        
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
    
    csrf_token = get_csrf_token()
    return await render_template('admin_r2_storage.html', active_page='r2_storage', r2_settings=r2_settings, settings=settings, csrf_token=csrf_token)

@bp.route('/r2-storage/global-toggle', methods=['POST'])
@require_admin
async def toggle_global_r2():
    try:
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                return jsonify({'error': 'Settings not found'}), 404
            
            settings.r2_storage_enabled = not settings.r2_storage_enabled
            await db_session.commit()
            
            return jsonify({
                'success': f'Global R2 Storage is now {"enabled" if settings.r2_storage_enabled else "disabled"}',
                'enabled': settings.r2_storage_enabled
            }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/r2-storage/add', methods=['POST'])
@require_admin
async def add_r2_storage():
    try:
        data = await request.get_json()
        
        if not data.get('bucket_name') or not data.get('access_key_id') or not data.get('secret_access_key'):
            return jsonify({'error': 'Missing required fields'}), 400
        
        async with AsyncSessionLocal() as db_session:
            new_r2 = CloudflareR2Settings(
                bucket_name=data.get('bucket_name'),
                access_key_id=data.get('access_key_id'),
                secret_access_key=data.get('secret_access_key'),
                account_id=data.get('account_id'),
                endpoint_url=data.get('endpoint_url'),
                region=data.get('region', 'us-east-1'),
                is_active=True
            )
            db_session.add(new_r2)
            await db_session.commit()
        
        return jsonify({'success': 'Cloudflare R2 storage added successfully', 'id': new_r2.id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/r2-storage/<int:r2_id>', methods=['PUT'])
@require_admin
async def update_r2_storage(r2_id):
    try:
        data = await request.get_json()
        
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(CloudflareR2Settings).where(CloudflareR2Settings.id == r2_id)
            )
            r2_setting = result.scalar_one_or_none()
            
            if not r2_setting:
                return jsonify({'error': 'R2 storage configuration not found'}), 404
            
            r2_setting.bucket_name = data.get('bucket_name', r2_setting.bucket_name)
            r2_setting.access_key_id = data.get('access_key_id', r2_setting.access_key_id)
            r2_setting.secret_access_key = data.get('secret_access_key', r2_setting.secret_access_key)
            r2_setting.account_id = data.get('account_id', r2_setting.account_id)
            r2_setting.endpoint_url = data.get('endpoint_url', r2_setting.endpoint_url)
            r2_setting.region = data.get('region', r2_setting.region)
            
            await db_session.commit()
        
        return jsonify({'success': 'R2 storage configuration updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/r2-storage/<int:r2_id>/toggle', methods=['POST'])
@require_admin
async def toggle_r2_storage(r2_id):
    try:
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(CloudflareR2Settings).where(CloudflareR2Settings.id == r2_id)
            )
            r2_setting = result.scalar_one_or_none()
            
            if not r2_setting:
                return jsonify({'error': 'R2 storage configuration not found'}), 404
            
            r2_setting.is_active = not r2_setting.is_active
            await db_session.commit()
        
        return jsonify({'success': f'R2 storage is now {"active" if r2_setting.is_active else "inactive"}'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/r2-storage/<int:r2_id>', methods=['DELETE'])
@require_admin
async def delete_r2_storage(r2_id):
    try:
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(CloudflareR2Settings).where(CloudflareR2Settings.id == r2_id)
            )
            r2_setting = result.scalar_one_or_none()
            
            if not r2_setting:
                return jsonify({'error': 'R2 storage configuration not found'}), 404
            
            await db_session.delete(r2_setting)
            await db_session.commit()
        
        return jsonify({'success': 'R2 storage configuration deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/r2-storage/<int:r2_id>/test', methods=['POST'])
@require_admin
async def test_r2_connection(r2_id):
    try:
        import boto3
        
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(CloudflareR2Settings).where(CloudflareR2Settings.id == r2_id)
            )
            r2_setting = result.scalar_one_or_none()
            
            if not r2_setting:
                return jsonify({'error': 'R2 storage configuration not found'}), 404
            
            s3_client = boto3.client(
                's3',
                endpoint_url=r2_setting.endpoint_url,
                aws_access_key_id=r2_setting.access_key_id,
                aws_secret_access_key=r2_setting.secret_access_key,
                region_name=r2_setting.region
            )
            
            s3_client.head_bucket(Bucket=r2_setting.bucket_name)
        
        return jsonify({'success': 'Connection successful! Cloudflare R2 is working properly'}), 200
    except Exception as e:
        return jsonify({'error': f'Connection failed: {str(e)}'}), 500
