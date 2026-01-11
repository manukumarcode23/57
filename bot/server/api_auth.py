from quart import request, jsonify
from bot.database import AsyncSessionLocal
from bot.models import ApiEndpointKey, Settings
from sqlalchemy import select
from functools import wraps
from os import environ

ENDPOINT_TOKEN_MAPPING = {
    'Ads API': 'ads_api_token',
    'Payment API': 'payment_api_token',
    'Subscription API': 'payment_api_token',
    'Payment Webhook': 'payment_api_token',
}

ENDPOINT_ENV_FALLBACK = {
    'Ads API': 'AD_API_TOKEN',
    'Payment API': 'PAYMENT_API_TOKEN',
    'Subscription API': 'PAYMENT_API_TOKEN',
    'Payment Webhook': 'PAYMENT_API_TOKEN',
}

async def validate_endpoint_api_key(endpoint_name: str) -> tuple[bool, str]:
    """
    Validate API key for a specific endpoint.
    Checks multiple locations: query params, JSON body, Authorization header, X-API-Key header.
    Priority order:
    1. Specific token from Settings (ads_api_token, payment_api_token)
    2. Global token from Settings (global_api_token)
    3. ApiEndpointKey model (admin-managed keys)
    4. Endpoint-specific env var (AD_API_TOKEN for Ads API, PAYMENT_API_TOKEN for Payment API)
    5. Global env var (GLOBAL_API_TOKEN)
    Returns (is_valid, error_message)
    """
    api_key = request.headers.get('X-API-Key') or request.headers.get('X-Api-Key')
    
    if not api_key:
        api_key = request.args.get('api_key') or request.args.get('token')
    
    if not api_key:
        try:
            if request.is_json:
                data = await request.get_json()
                if data:
                    api_key = data.get('api_key') or data.get('token')
        except Exception:
            pass
    
    if not api_key:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            api_key = auth_header[7:]
    
    if not api_key:
        return False, 'API key is required (provide via X-API-Key header, token query param, JSON body, or Authorization header)'
    
    async with AsyncSessionLocal() as db_session:
        try:
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            
            if settings:
                token_field = ENDPOINT_TOKEN_MAPPING.get(endpoint_name)
                if token_field:
                    specific_token = getattr(settings, token_field, None)
                    if specific_token and api_key == specific_token:
                        return True, ''
                
                if settings.global_api_token and api_key == settings.global_api_token:
                    return True, ''
            
            result = await db_session.execute(
                select(ApiEndpointKey).where(
                    ApiEndpointKey.endpoint_name == endpoint_name,
                    ApiEndpointKey.api_key == api_key,
                    ApiEndpointKey.is_active == True
                )
            )
            endpoint_key = result.scalar_one_or_none()
            
            if endpoint_key:
                return True, ''
            
            env_var_name = ENDPOINT_ENV_FALLBACK.get(endpoint_name, 'AD_API_TOKEN')
            fallback_token = environ.get(env_var_name)
            if fallback_token and api_key == fallback_token:
                return True, ''
            
            global_env_token = environ.get('GLOBAL_API_TOKEN')
            if global_env_token and api_key == global_env_token:
                return True, ''
            
            return False, 'Invalid or inactive API key'
        except Exception as e:
            return False, 'Error validating API key'

def require_endpoint_api_key(endpoint_name: str):
    """
    Decorator to require valid API key for a specific endpoint.
    Usage: @require_endpoint_api_key('API Request')
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            is_valid, error_msg = await validate_endpoint_api_key(endpoint_name)
            
            if not is_valid:
                return jsonify({
                    'status': 'error',
                    'message': error_msg
                }), 401
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
