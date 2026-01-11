import asyncio
from quart import Blueprint, request, render_template, redirect
from bot.database import AsyncSessionLocal
from bot.models import Settings
from sqlalchemy import select
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token
from pathlib import Path
from secrets import token_hex
import os

bp = Blueprint('admin_settings', __name__)

@bp.route('/settings')
@require_admin
async def settings():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(Settings))
        settings = result.scalar_one_or_none()
        
        if not settings:
            settings = Settings(
                terms_of_service='',
                privacy_policy='',
                impression_rate=0.0,
                impression_cutback_percentage=0.0,
                web_max_file_size_mb=2048,
                web_upload_rate_limit=10,
                web_upload_rate_window=3600,
                api_rate_limit=100,
                api_rate_window=3600
            )
            db_session.add(settings)
            await db_session.commit()
    
    csrf_token = get_csrf_token()
    return await render_template('admin_settings.html', active_page='settings', settings=settings, csrf_token=csrf_token)

@bp.route('/settings/update', methods=['POST'])
@require_admin
@csrf_protect
async def update_settings():
    data = await request.form
    files = await request.files
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = Settings()
                db_session.add(settings)
            
            settings.terms_of_service = data.get('terms_of_service', '').strip()
            settings.privacy_policy = data.get('privacy_policy', '').strip()
            
            try:
                impression_rate_str = str(data.get('impression_rate', '0')).strip()
                if not impression_rate_str or impression_rate_str.lower() == 'none' or impression_rate_str == '':
                    settings.impression_rate = 0.0
                else:
                    settings.impression_rate = float(impression_rate_str)
            except (ValueError, TypeError, Exception):
                settings.impression_rate = 0.0
            
            try:
                impression_cutback_str = str(data.get('impression_cutback_percentage', '0')).strip()
                if not impression_cutback_str or impression_cutback_str.lower() == 'none' or impression_cutback_str == '':
                    settings.impression_cutback_percentage = 0.0
                else:
                    settings.impression_cutback_percentage = float(impression_cutback_str)
            except (ValueError, TypeError, Exception):
                settings.impression_cutback_percentage = 0.0

            # Handle other numeric fields to prevent "Invalid number format"
            try:
                web_max_val = data.get('web_max_file_size_mb', '2048')
                settings.web_max_file_size_mb = int(web_max_val) if (web_max_val and str(web_max_val).lower() != 'none') else 2048
            except (ValueError, TypeError, Exception):
                settings.web_max_file_size_mb = 2048

            try:
                web_up_limit = data.get('web_upload_rate_limit', '10')
                settings.web_upload_rate_limit = int(web_up_limit) if (web_up_limit and str(web_up_limit).lower() != 'none') else 10
            except (ValueError, TypeError, Exception):
                settings.web_upload_rate_limit = 10

            try:
                web_up_window = data.get('web_upload_rate_window', '3600')
                settings.web_upload_rate_window = int(web_up_window) if (web_up_window and str(web_up_window).lower() != 'none') else 3600
            except (ValueError, TypeError, Exception):
                settings.web_upload_rate_window = 3600

            try:
                api_req_limit = data.get('api_rate_limit', '100')
                settings.api_rate_limit = int(api_req_limit) if (api_req_limit and str(api_req_limit).lower() != 'none') else 100
            except (ValueError, TypeError, Exception):
                settings.api_rate_limit = 100

            try:
                api_req_window = data.get('api_rate_window', '3600')
                settings.api_rate_window = int(api_req_window) if (api_req_window and str(api_req_window).lower() != 'none') else 3600
            except (ValueError, TypeError, Exception):
                settings.api_rate_window = 3600
            
            settings.maintenance_mode = data.get('maintenance_mode') == 'on'
            
            # Paytm payment gateway settings
            settings.paytm_mid = data.get('paytm_mid', '').strip()
            settings.paytm_upi_id = data.get('paytm_upi_id', '').strip()
            settings.paytm_unit_id = data.get('paytm_unit_id', '').strip()
            settings.paytm_signature = data.get('paytm_signature', '').strip()
            
            # API token settings
            settings.global_api_token = data.get('global_api_token', '').strip() or None
            settings.ads_api_token = data.get('ads_api_token', '').strip() or None
            settings.payment_api_token = data.get('payment_api_token', '').strip() or None
            
            # IPQS settings
            settings.ipqs_enabled = data.get('ipqs_enabled') == 'on'
            settings.ipqs_api_key = data.get('ipqs_api_key', '').strip() or None
            settings.ipqs_secret_key = data.get('ipqs_secret_key', '').strip() or None
            
            # R2 Storage settings
            settings.r2_storage_enabled = data.get('r2_storage_enabled') == 'on'
            
            # Website settings
            settings.website_name = data.get('website_name', 'CloudShare Pro').strip()
            
            # Handle logo upload
            if 'logo' in files:
                logo_file = files['logo']
                if logo_file and logo_file.filename:
                    branding_dir = Path('bot/server/static/branding')
                    branding_dir.mkdir(parents=True, exist_ok=True)
                    
                    file_ext = Path(logo_file.filename).suffix.lower()
                    if file_ext not in ['.png', '.jpg', '.jpeg', '.svg', '.webp']:
                        file_ext = '.png'
                    
                    # Force a name change to ensure DB update triggers cache bust
                    logo_filename = f'logo_{token_hex(4)}{file_ext}'
                    filepath = branding_dir / logo_filename
                    
                    # Log the attempt
                    print(f"Attempting to save logo: {logo_file.filename} to {filepath}")
                    
                    # Correct way to read file in Quart: it's an awaitable
                    # Ensure we don't try to await it if it's already bytes
                    file_data = logo_file.read()
                    if hasattr(file_data, '__await__') or asyncio.iscoroutine(file_data):
                        file_data = await file_data
                    
                    if file_data and len(file_data) > 0:
                        # Clean up old logo files
                        for old_logo in branding_dir.glob('logo_*'):
                            try:
                                os.remove(old_logo)
                                print(f"Removed old logo: {old_logo}")
                            except: pass

                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                            f.flush()
                            os.fsync(f.fileno())
                        
                        # Verify file exists after writing
                        if filepath.exists():
                            settings.logo_path = f'branding/{logo_filename}'
                            print(f"✓ Logo saved and verified: {settings.logo_path} ({len(file_data)} bytes)")
                        else:
                            print(f"✗ Failed to verify logo file after write: {filepath}")
                    else:
                        print(f"✗ No file data received for logo or empty file")
            
            # Handle favicon upload
            if 'favicon' in files:
                favicon_file = files['favicon']
                if favicon_file and favicon_file.filename:
                    branding_dir = Path('bot/server/static/branding')
                    branding_dir.mkdir(parents=True, exist_ok=True)
                    
                    file_ext = Path(favicon_file.filename).suffix.lower()
                    if file_ext not in ['.png', '.jpg', '.jpeg', '.ico', '.svg']:
                        file_ext = '.png'
                    
                    fav_filename = f'favicon_{token_hex(4)}{file_ext}'
                    filepath = branding_dir / fav_filename
                    
                    print(f"Attempting to save favicon: {favicon_file.filename} to {filepath}")
                    
                    # Correct way to read file in Quart: it's an awaitable
                    file_data = favicon_file.read()
                    if hasattr(file_data, '__await__') or asyncio.iscoroutine(file_data):
                        file_data = await file_data
                    
                    if file_data and len(file_data) > 0:
                        # Clean up old favicons
                        for old_fav in branding_dir.glob('favicon_*'):
                            try:
                                os.remove(old_fav)
                                print(f"Removed old favicon: {old_fav}")
                            except: pass

                        with open(filepath, 'wb') as f:
                            f.write(file_data)
                            f.flush()
                            os.fsync(f.fileno())
                        
                        # Verify file exists after writing
                        if filepath.exists():
                            settings.favicon_path = f'branding/{fav_filename}'
                            print(f"✓ Favicon saved and verified: {settings.favicon_path} ({len(file_data)} bytes)")
                        else:
                            print(f"✗ Failed to verify favicon file after write: {filepath}")
                    else:
                        print(f"✗ No file data received for favicon or empty file")
            
            # Handle default thumbnail template upload
            if 'default_thumbnail' in files:
                thumbnail_file = files['default_thumbnail']
                if thumbnail_file and thumbnail_file.filename:
                    templates_dir = Path('bot/server/static/templates')
                    templates_dir.mkdir(parents=True, exist_ok=True)
                    
                    file_ext = Path(thumbnail_file.filename).suffix.lower()
                    if file_ext not in ['.png', '.jpg', '.jpeg']:
                        file_ext = '.png'
                    
                    filename = f'default_thumbnail_{token_hex(8)}{file_ext}'
                    filepath = templates_dir / filename
                    
                    file_data = await thumbnail_file.read()
                    
                    with open(filepath, 'wb') as f:
                        f.write(file_data)
                    
                    if settings.default_thumbnail_path and Path(f'bot/server/static/{settings.default_thumbnail_path}').exists():
                        try:
                            os.remove(f'bot/server/static/{settings.default_thumbnail_path}')
                        except OSError:
                            pass
                    
                    settings.default_thumbnail_path = f'templates/{filename}'
            
            try:
                await db_session.commit()
                # Print to logs for debugging
                print("✓ Settings and logo saved successfully to database")
                
                # Refresh session or settings object to ensure the latest data is picked up
                await db_session.refresh(settings)
                
            except Exception as e:
                await db_session.rollback()
                print(f"✗ Database commit error: {e}")
                return redirect('/admin/settings')
            
            return redirect('/admin/settings?updated=true')
            
        except Exception as e:
            await db_session.rollback()
            print(f"✗ General settings update error: {e}")
            return redirect('/admin/settings')
