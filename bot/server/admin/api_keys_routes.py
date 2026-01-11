from quart import Blueprint, request, render_template, redirect, jsonify
from bot.database import AsyncSessionLocal
from bot.models import ApiEndpointKey
from sqlalchemy import select, text
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token
from secrets import token_hex
import logging

logger = logging.getLogger(__name__)
bp = Blueprint('admin_api_keys', __name__)

# Default API keys to create automatically
DEFAULT_API_KEYS = [
    {
        'endpoint_name': 'Payment API',
        'endpoint_path': '/api/payment/*',
        'description': 'API key for payment endpoints including create-qr, check-status, plans, subscription-status, and expire. Used for Paytm/UPI payment processing.'
    },
    {
        'endpoint_name': 'Ads API',
        'endpoint_path': '/api/ads/*',
        'description': 'API key for advertisement-related endpoints. Used for serving and tracking ad impressions and clicks.'
    },
    {
        'endpoint_name': 'Subscription API',
        'endpoint_path': '/api/subscription/*',
        'description': 'API key for subscription management endpoints. Used for checking and managing user subscription status.'
    },
    {
        'endpoint_name': 'Payment Webhook',
        'endpoint_path': '/api/payment/webhook',
        'description': 'API key for payment webhook callbacks. Used by payment gateways to notify about transaction status changes.'
    }
]

async def initialize_default_api_keys():
    """Create default API keys if they don't exist"""
    async with AsyncSessionLocal() as db_session:
        try:
            # Ensure table structure is updated to allow duplicate keys
            try:
                # We need to explicitly name the constraint if we want to drop it accurately
                # But typically it's api_endpoint_keys_api_key_key
                await db_session.execute(text("ALTER TABLE api_endpoint_keys DROP CONSTRAINT IF EXISTS api_endpoint_keys_api_key_key"))
                # Also drop any other unique constraints on api_key if they exist with different names
                await db_session.execute(text("""
                    DO $$ 
                    DECLARE 
                        r RECORD;
                    BEGIN
                        FOR r IN (SELECT conname 
                                  FROM pg_constraint 
                                  WHERE conrelid = 'api_endpoint_keys'::regclass 
                                  AND contype = 'u') 
                        LOOP
                            EXECUTE 'ALTER TABLE api_endpoint_keys DROP CONSTRAINT ' || r.conname;
                        END LOOP;
                    END $$;
                """))
                await db_session.execute(text("DROP INDEX IF EXISTS idx_api_endpoint_keys_api_key"))
                await db_session.execute(text("CREATE INDEX IF NOT EXISTS idx_api_endpoint_keys_api_key ON api_endpoint_keys(api_key)"))
                await db_session.commit()
            except Exception as e:
                await db_session.rollback()
                logger.error(f"Non-critical error during schema update: {e}")
            
            for default_key in DEFAULT_API_KEYS:
                # Check if this endpoint already exists
                result = await db_session.execute(
                    select(ApiEndpointKey).where(
                        ApiEndpointKey.endpoint_path == default_key['endpoint_path']
                    )
                )
                existing = result.scalar_one_or_none()
                
                if not existing:
                    new_key = ApiEndpointKey(
                        endpoint_name=default_key['endpoint_name'],
                        endpoint_path=default_key['endpoint_path'],
                        api_key=token_hex(32),
                        description=default_key['description'],
                        is_active=True
                    )
                    db_session.add(new_key)
            
            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error initializing default API keys: {e}")

@bp.route('/api-keys')
@require_admin
async def api_keys():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(ApiEndpointKey).order_by(ApiEndpointKey.endpoint_name)
        )
        api_keys = result.scalars().all()
    
    csrf_token = get_csrf_token()
    return await render_template('admin_api_keys.html', active_page='api_keys', api_keys=api_keys, csrf_token=csrf_token)

@bp.route('/api-keys/add', methods=['POST'])
@require_admin
@csrf_protect
async def add_api_key():
    data = await request.form
    
    endpoint_name = data.get('endpoint_name', '').strip()
    endpoint_path = data.get('endpoint_path', '').strip()
    description = data.get('description', '').strip()
    manual_api_key = data.get('api_key', '').strip()
    
    if not endpoint_name or not endpoint_path:
        return redirect('/admin/api-keys?error=Name and path are required')
    
    # Use manual API key if provided, otherwise generate a secure one
    api_key = manual_api_key if manual_api_key else token_hex(32)
    
    async with AsyncSessionLocal() as db_session:
        try:
            new_key = ApiEndpointKey(
                endpoint_name=endpoint_name,
                endpoint_path=endpoint_path,
                api_key=api_key,
                description=description,
                is_active=True
            )
            db_session.add(new_key)
            await db_session.commit()
            return redirect('/admin/api-keys?success=API key added successfully')
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error adding API key: {e}")
            return redirect('/admin/api-keys?error=Failed to add API key')

@bp.route('/api-keys/edit/<int:key_id>', methods=['POST'])
@require_admin
@csrf_protect
async def edit_api_key(key_id: int):
    data = await request.form
    
    endpoint_name = data.get('endpoint_name', '').strip()
    endpoint_path = data.get('endpoint_path', '').strip()
    description = data.get('description', '').strip()
    manual_api_key = data.get('api_key', '').strip()
    
    if not endpoint_name or not endpoint_path:
        return redirect('/admin/api-keys?error=Name and path are required')
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(ApiEndpointKey).where(ApiEndpointKey.id == key_id)
            )
            api_key = result.scalar_one_or_none()
            
            if not api_key:
                return redirect('/admin/api-keys?error=API key not found')
            
            api_key.endpoint_name = endpoint_name
            api_key.endpoint_path = endpoint_path
            api_key.description = description
            
            if manual_api_key:
                api_key.api_key = manual_api_key
            
            await db_session.commit()
            return redirect('/admin/api-keys?success=API key updated successfully')
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error updating API key: {e}")
            return redirect('/admin/api-keys?error=Failed to update API key')

@bp.route('/api-keys/toggle/<int:key_id>', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_api_key(key_id: int):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(ApiEndpointKey).where(ApiEndpointKey.id == key_id)
            )
            api_key = result.scalar_one_or_none()
            
            if not api_key:
                return redirect('/admin/api-keys?error=API key not found')
            
            api_key.is_active = not api_key.is_active
            await db_session.commit()
            
            status = 'enabled' if api_key.is_active else 'disabled'
            return redirect(f'/admin/api-keys?success=API key {status} successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/api-keys?error=Failed to toggle API key status')

@bp.route('/api-keys/regenerate/<int:key_id>', methods=['POST'])
@require_admin
@csrf_protect
async def regenerate_api_key(key_id: int):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(ApiEndpointKey).where(ApiEndpointKey.id == key_id)
            )
            api_key = result.scalar_one_or_none()
            
            if not api_key:
                return redirect('/admin/api-keys?error=API key not found')
            
            # Generate new API key
            api_key.api_key = token_hex(32)
            await db_session.commit()
            
            return redirect('/admin/api-keys?success=API key regenerated successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/api-keys?error=Failed to regenerate API key')

@bp.route('/api-keys/delete/<int:key_id>', methods=['POST'])
@require_admin
@csrf_protect
async def delete_api_key(key_id: int):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(ApiEndpointKey).where(ApiEndpointKey.id == key_id)
            )
            api_key = result.scalar_one_or_none()
            
            if not api_key:
                return redirect('/admin/api-keys?error=API key not found')
            
            await db_session.delete(api_key)
            await db_session.commit()
            
            return redirect('/admin/api-keys?success=API key deleted successfully')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/api-keys?error=Failed to delete API key')
