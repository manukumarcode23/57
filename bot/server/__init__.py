from quart import Quart, make_response, render_template, request, session
from uvicorn import Server as UvicornServer, Config
from logging import getLogger
from bot.config import Server, LOGGER_CONFIG_JSON
from bot.database import init_db, close_db
from secrets import token_hex
from datetime import timedelta
from pathlib import Path

from . import main, error, auth, admin, publisher, ad_api, payment_api

logger = getLogger('uvicorn')

static_folder = Path(__file__).parent / 'static'
template_folder = Path(__file__).parent / 'templates'

instance = Quart(
    __name__,
    static_folder=str(static_folder),
    static_url_path='/static',
    template_folder=str(template_folder)
)
instance.config['RESPONSE_TIMEOUT'] = 300
instance.config['REQUEST_TIMEOUT'] = 300
instance.config['MAX_CONTENT_LENGTH'] = Server.MAX_FILE_SIZE

from os import environ

# Secure default SECRET_KEY for development
# IMPORTANT: Set SECRET_KEY in Replit Secrets for production!
DEFAULT_SECRET_KEY = 'dev_secret_key_not_for_production_replace_in_replit_secrets_123456'

# Use environment variable SECRET_KEY or secure default
instance.config['SECRET_KEY'] = environ.get('SECRET_KEY') or DEFAULT_SECRET_KEY

instance.config['SESSION_COOKIE_SECURE'] = environ.get('ENVIRONMENT', 'production') != 'development'
instance.config['SESSION_COOKIE_HTTPONLY'] = True
instance.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
instance.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
instance.config['SESSION_COOKIE_NAME'] = 'session'

@instance.after_request
async def add_security_headers(response):
    """Add security headers to all responses"""
    # Prevent XSS attacks
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Content Security Policy - Allow CDN resources for Tailwind CSS, Chart.js, and Google Fonts
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://cdn.tailwindcss.com;"
    
    # Disable caching for static branding assets to ensure immediate updates
    if request.path.startswith('/static/branding/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Expires'] = '0'
    
    # Prevent caching of sensitive pages
    elif request.path.startswith('/admin') or request.path.startswith('/publisher'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    
    return response

@instance.context_processor
async def inject_settings():
    """Make settings available to all templates"""
    from bot.database import AsyncSessionLocal
    from bot.models import Settings
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            return {
                'settings': settings,
                'app_logo': settings.logo_path if settings and settings.logo_path else None,
                'app_favicon': settings.favicon_path if settings and settings.favicon_path else None
            }
        except Exception:
            return {
                'settings': None,
                'app_logo': None,
                'app_favicon': None
            }

@instance.before_request
async def check_maintenance_mode():
    """Check if maintenance mode is enabled and block non-admin access"""
    from bot.database import AsyncSessionLocal
    from bot.models import Settings
    from sqlalchemy import select
    
    # Allow access to static files, login page, and admin routes
    if request.path.startswith('/static/') or request.path.startswith('/login') or request.path.startswith('/admin'):
        return None
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(Settings))
        settings = result.scalar_one_or_none()
        
        if settings and settings.maintenance_mode:
            is_admin = session.get('is_admin', False)
            
            if not is_admin:
                return await render_template('maintenance.html')

@instance.before_serving
async def before_serve():
    await init_db()
    
    # Initialize default API keys automatically
    from bot.server.admin.api_keys_routes import initialize_default_api_keys
    await initialize_default_api_keys()
    logger.info('✓ Default API keys initialized')
    
    # Log SECRET_KEY status (never log the actual key!)
    if environ.get('SECRET_KEY'):
        logger.info('✓ Using SECRET_KEY from Replit Secrets (secure)')
    else:
        logger.warning('⚠ Using default SECRET_KEY - Set SECRET_KEY in Replit Secrets for production!')
    
    logger.info('Web server is started!')
    logger.info(f'Server running on {Server.BIND_ADDRESS}:{Server.PORT}')

@instance.after_serving
async def after_serve():
    await close_db()
    logger.info('Web server is shutting down!')

instance.register_blueprint(main.bp)
instance.register_blueprint(auth.bp)
instance.register_blueprint(admin.bp)
instance.register_blueprint(publisher.bp)
instance.register_blueprint(ad_api.bp)
instance.register_blueprint(payment_api.bp)

@instance.errorhandler(400)
async def handle_invalid_request(e):
    return await make_response('Invalid request.', 400)

@instance.errorhandler(404)  
async def handle_not_found(e):
    return await render_template('404.html'), 404

@instance.errorhandler(405)
async def handle_invalid_method(e):
    return await make_response('Invalid request method.', 405)

@instance.errorhandler(error.HTTPError)
async def handle_http_error(e):
    error_message = error.error_messages.get(e.status_code)
    return await make_response(e.description or error_message or 'Unknown error', e.status_code)

server = UvicornServer (
    Config (
        app=instance,
        host=Server.BIND_ADDRESS,
        port=Server.PORT,
        log_config=LOGGER_CONFIG_JSON,
        timeout_keep_alive=300,
        timeout_graceful_shutdown=30
    )
)