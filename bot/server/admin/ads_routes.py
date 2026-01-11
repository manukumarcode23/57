from quart import Blueprint, request, render_template, redirect
from bot.database import AsyncSessionLocal
from bot.models import AdNetwork, ApiEndpointKey
from sqlalchemy import select, delete
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token
import logging

bp = Blueprint('admin_ads', __name__)
logger = logging.getLogger('bot.server')

@bp.route('/ad-networks')
@require_admin
async def ad_networks():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(AdNetwork).order_by(AdNetwork.priority)
        )
        networks = result.scalars().all()
        
        api_key_result = await db_session.execute(
            select(ApiEndpointKey).where(
                ApiEndpointKey.endpoint_name == 'Ads API',
                ApiEndpointKey.is_active == True
            )
        )
        api_key_record = api_key_result.scalar_one_or_none()
        ads_api_configured = api_key_record is not None
        
    csrf_token = get_csrf_token()
    return await render_template('admin_ad_networks.html', active_page='ad_networks', networks=networks, ads_api_configured=ads_api_configured, csrf_token=csrf_token)

@bp.route('/ad-networks/add', methods=['POST'])
@require_admin
@csrf_protect
async def add_ad_network():
    data = await request.form
    
    async with AsyncSessionLocal() as db_session:
        try:
            banner_limit_str = data.get('banner_daily_limit', '0').strip()
            interstitial_limit_str = data.get('interstitial_daily_limit', '0').strip()
            rewarded_limit_str = data.get('rewarded_daily_limit', '0').strip()
            priority_str = data.get('priority', '1').strip()
            
            try:
                banner_daily_limit = int(banner_limit_str) if banner_limit_str else 0
                interstitial_daily_limit = int(interstitial_limit_str) if interstitial_limit_str else 0
                rewarded_daily_limit = int(rewarded_limit_str) if rewarded_limit_str else 0
                priority = int(priority_str) if priority_str else 1
            except ValueError as e:
                logger.error(f"Invalid integer value in ad network form: {e}")
                await db_session.rollback()
                return redirect('/admin/ad-networks')
            
            network = AdNetwork(
                network_name=data.get('network_name', '').strip(),
                banner_id=data.get('banner_id', '').strip() or None,
                interstitial_id=data.get('interstitial_id', '').strip() or None,
                rewarded_id=data.get('rewarded_id', '').strip() or None,
                banner_daily_limit=banner_daily_limit,
                interstitial_daily_limit=interstitial_daily_limit,
                rewarded_daily_limit=rewarded_daily_limit,
                status=data.get('status', 'active'),
                priority=priority
            )
            
            db_session.add(network)
            await db_session.commit()
            
            return redirect('/admin/ad-networks')
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error adding ad network: {e}")
            return redirect('/admin/ad-networks')

@bp.route('/ad-networks/edit/<int:network_id>', methods=['POST'])
@require_admin
@csrf_protect
async def edit_ad_network(network_id):
    data = await request.form
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(AdNetwork).where(AdNetwork.id == network_id)
            )
            network = result.scalar_one_or_none()
            
            if network:
                banner_limit_str = data.get('banner_daily_limit', '0').strip()
                interstitial_limit_str = data.get('interstitial_daily_limit', '0').strip()
                rewarded_limit_str = data.get('rewarded_daily_limit', '0').strip()
                priority_str = data.get('priority', '1').strip()
                
                try:
                    banner_daily_limit = int(banner_limit_str) if banner_limit_str else 0
                    interstitial_daily_limit = int(interstitial_limit_str) if interstitial_limit_str else 0
                    rewarded_daily_limit = int(rewarded_limit_str) if rewarded_limit_str else 0
                    priority = int(priority_str) if priority_str else 1
                except ValueError as e:
                    logger.error(f"Invalid integer value in ad network edit form: {e}")
                    await db_session.rollback()
                    return redirect('/admin/ad-networks')
                
                network.network_name = data.get('network_name', '').strip()
                network.banner_id = data.get('banner_id', '').strip() or None
                network.interstitial_id = data.get('interstitial_id', '').strip() or None
                network.rewarded_id = data.get('rewarded_id', '').strip() or None
                network.banner_daily_limit = banner_daily_limit
                network.interstitial_daily_limit = interstitial_daily_limit
                network.rewarded_daily_limit = rewarded_daily_limit
                network.status = data.get('status', 'active')
                network.priority = priority
                
                await db_session.commit()
            
            return redirect('/admin/ad-networks')
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error editing ad network: {e}")
            return redirect('/admin/ad-networks')

@bp.route('/ad-networks/toggle/<int:network_id>', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_ad_network(network_id):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(AdNetwork).where(AdNetwork.id == network_id)
            )
            network = result.scalar_one_or_none()
            
            if network:
                network.status = 'inactive' if network.status == 'active' else 'active'
                await db_session.commit()
            
            return redirect('/admin/ad-networks')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/ad-networks')

@bp.route('/ad-networks/delete/<int:network_id>', methods=['POST'])
@require_admin
@csrf_protect
async def delete_ad_network(network_id):
    async with AsyncSessionLocal() as db_session:
        try:
            stmt = delete(AdNetwork).where(AdNetwork.id == network_id)
            await db_session.execute(stmt)
            await db_session.commit()
            
            return redirect('/admin/ad-networks')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/ad-networks')
