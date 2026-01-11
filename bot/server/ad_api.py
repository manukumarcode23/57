from quart import Blueprint, request, jsonify
from bot.database import AsyncSessionLocal
from bot.models import AdNetwork, AdPlayCount, AdPlayTracking, ApiEndpointKey
from bot.modules.geoip import get_location_from_ip
from sqlalchemy import select, and_, func
from os import environ
from functools import wraps
from datetime import date, datetime, timezone
from secrets import token_hex
from urllib.parse import urlencode

bp = Blueprint('ad_api', __name__, url_prefix='/api')

def build_api_link(endpoint: str, token: str, android_id: str | None = None) -> str:
    """Build API link with properly URL-encoded query parameters"""
    base_url = environ.get('BASE_URL', 'http://localhost:5000')
    params = {'token': token}
    if android_id:
        params['android_id'] = android_id
    query_string = urlencode(params)
    return f"{base_url}/api/{endpoint}?{query_string}"

def get_client_ip() -> str:
    """Extract client IP from request headers with proper priority"""
    cf_connecting_ip = request.headers.get('CF-Connecting-IP', '').strip()
    if cf_connecting_ip:
        return cf_connecting_ip
    
    x_real_ip = request.headers.get('X-Real-IP', '').strip()
    if x_real_ip:
        return x_real_ip
    
    x_forwarded_for = request.headers.get('X-Forwarded-For', '').strip()
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    
    return request.remote_addr or '0.0.0.0'

async def get_request_location():
    """Get country and region information from the current request's IP"""
    user_ip = get_client_ip()
    country_code, country_name, region = await get_location_from_ip(user_ip)
    return {
        'country_code': country_code,
        'country_name': country_name,
        'region': region,
        'user_ip': user_ip
    }

def require_api_token(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        token = request.args.get('token')
        
        if not token:
            return jsonify({'status': 'error', 'message': 'Missing token parameter'}), 401
        
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(ApiEndpointKey).where(
                    ApiEndpointKey.endpoint_name == 'Ads API',
                    ApiEndpointKey.is_active == True
                )
            )
            api_key_record = result.scalar_one_or_none()
            
            if not api_key_record:
                fallback_token = environ.get('AD_API_TOKEN')
                if not fallback_token:
                    return jsonify({'status': 'error', 'message': 'API token not configured'}), 500
                
                if token != fallback_token:
                    return jsonify({'status': 'error', 'message': 'Invalid token'}), 401
            else:
                if token != api_key_record.api_key:
                    return jsonify({'status': 'error', 'message': 'Invalid token'}), 401
        
        return await func(*args, **kwargs)
    return wrapper

async def get_or_create_play_count(db_session, ad_network_id: int, ad_type: str, android_id: str | None = None, user_ip: str | None = None):
    """Get or create play count for today - uses SELECT FOR UPDATE to prevent race conditions"""
    today = date.today()
    
    if android_id:
        query_condition = and_(
            AdPlayCount.ad_network_id == ad_network_id,
            AdPlayCount.ad_type == ad_type,
            AdPlayCount.play_date == today,
            AdPlayCount.android_id == android_id
        )
    else:
        query_condition = and_(
            AdPlayCount.ad_network_id == ad_network_id,
            AdPlayCount.ad_type == ad_type,
            AdPlayCount.play_date == today,
            AdPlayCount.user_ip == user_ip
        )
    
    # Use SELECT FOR UPDATE to prevent race conditions
    result = await db_session.execute(
        select(AdPlayCount).where(query_condition).with_for_update()
    )
    play_count = result.scalar_one_or_none()
    
    if not play_count:
        # No existing record, create one
        play_count = AdPlayCount(
            ad_network_id=ad_network_id,
            ad_type=ad_type,
            android_id=android_id,
            user_ip=user_ip,
            play_date=today,
            play_count=0
        )
        db_session.add(play_count)
        # Flush to ensure the record is created and locked
        await db_session.flush()
    
    return play_count

async def create_tracking_token(db_session, network, ad_type: str, ad_unit_id: str, android_id: str | None, user_ip: str | None, location: dict):
    """Create a unique tracking token for an ad request"""
    tracking_token = token_hex(32)
    
    tracking_record = AdPlayTracking(
        tracking_token=tracking_token,
        ad_network_id=network.id,
        network_name=network.network_name,
        ad_type=ad_type,
        ad_unit_id=ad_unit_id,
        android_id=android_id,
        user_ip=user_ip,
        country_code=location.get('country_code'),
        country_name=location.get('country_name'),
        region=location.get('region'),
        is_played=False
    )
    db_session.add(tracking_record)
    await db_session.flush()
    
    return tracking_token

async def find_available_ad_network(db_session, ad_type: str, android_id: str | None = None, user_ip: str | None = None):
    """Find the first available ad network based on daily limits and priority - returns (network, play_count)"""
    result = await db_session.execute(
        select(AdNetwork)
        .where(AdNetwork.status == 'active')
        .order_by(AdNetwork.priority)
    )
    ad_networks = result.scalars().all()
    
    today = date.today()
    
    for network in ad_networks:
        # Check if this network has the requested ad type
        if ad_type == 'banner' and not network.banner_id:
            continue
        elif ad_type == 'interstitial' and not network.interstitial_id:
            continue
        elif ad_type == 'rewarded' and not network.rewarded_id:
            continue
        
        # Get daily limit for this ad type
        if ad_type == 'banner':
            daily_limit = network.banner_daily_limit
        elif ad_type == 'interstitial':
            daily_limit = network.interstitial_daily_limit
        else:  # rewarded
            daily_limit = network.rewarded_daily_limit
        
        # If limit is 0, it means unlimited
        if daily_limit == 0:
            play_count = await get_or_create_play_count(db_session, network.id, ad_type, android_id, user_ip)
            return (network, play_count)
        
        # Check current play count for today
        play_count = await get_or_create_play_count(db_session, network.id, ad_type, android_id, user_ip)
        
        # If under the limit, return this network and play count record
        if play_count.play_count < daily_limit:
            return (network, play_count)
    
    return (None, None)

@bp.route('/banner_ads')
@require_api_token
async def get_banner_ads():
    android_id = request.args.get('android_id') or None
    user_ip = get_client_ip() if not android_id else None
    
    async with AsyncSessionLocal() as db_session:
        try:
            location = await get_request_location()
            
            result = await db_session.execute(
                select(AdNetwork)
                .where(AdNetwork.status == 'active')
                .order_by(AdNetwork.priority)
            )
            ad_networks = result.scalars().all()
            
            banner_ads = []
            for network in ad_networks:
                if network.banner_id:
                    play_count = await get_or_create_play_count(
                        db_session, network.id, 'banner', android_id, user_ip
                    )
                    
                    # Check if limit is reached
                    limit_reached = network.banner_daily_limit > 0 and play_count.play_count >= network.banner_daily_limit
                    
                    ad_data = {
                        'network_id': network.id,
                        'network_name': network.network_name,
                        'ad_type': 'banner',
                        'ad_unit_id': network.banner_id,
                        'priority': network.priority,
                        'daily_limit': network.banner_daily_limit,
                        'current_plays': play_count.play_count,
                        'remaining': max(0, network.banner_daily_limit - play_count.play_count) if network.banner_daily_limit > 0 else -1,
                        'limit_reached': limit_reached,
                        'unlimited': network.banner_daily_limit == 0
                    }
                    
                    # Only generate unique_id if limit not reached
                    if not limit_reached:
                        tracking_token = await create_tracking_token(
                            db_session, network, 'banner', network.banner_id, 
                            android_id, user_ip, location
                        )
                        ad_data['unique_id'] = tracking_token
                    
                    banner_ads.append(ad_data)
            
            await db_session.commit()
            
            if not banner_ads:
                return jsonify({
                    'status': 'error',
                    'message': 'No banner ads available'
                }), 404
            
            return jsonify({
                'status': 'success',
                'type': 'banner',
                'total': len(banner_ads),
                'ads': banner_ads,
                'tracking_id': android_id if android_id else user_ip,
                'country': location['country_name'],
                'country_code': location['country_code'],
                'region': location['region']
            }), 200
        except Exception as e:
            await db_session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Failed to fetch banner ads: {str(e)}'
            }), 500

@bp.route('/interstitial_ads')
@require_api_token
async def get_interstitial_ads():
    android_id = request.args.get('android_id') or None
    user_ip = get_client_ip() if not android_id else None
    
    async with AsyncSessionLocal() as db_session:
        try:
            location = await get_request_location()
            
            result = await db_session.execute(
                select(AdNetwork)
                .where(AdNetwork.status == 'active')
                .order_by(AdNetwork.priority)
            )
            ad_networks = result.scalars().all()
            
            interstitial_ads = []
            for network in ad_networks:
                if network.interstitial_id:
                    play_count = await get_or_create_play_count(
                        db_session, network.id, 'interstitial', android_id, user_ip
                    )
                    
                    # Check if limit is reached
                    limit_reached = network.interstitial_daily_limit > 0 and play_count.play_count >= network.interstitial_daily_limit
                    
                    ad_data = {
                        'network_id': network.id,
                        'network_name': network.network_name,
                        'ad_type': 'interstitial',
                        'ad_unit_id': network.interstitial_id,
                        'priority': network.priority,
                        'daily_limit': network.interstitial_daily_limit,
                        'current_plays': play_count.play_count,
                        'remaining': max(0, network.interstitial_daily_limit - play_count.play_count) if network.interstitial_daily_limit > 0 else -1,
                        'limit_reached': limit_reached,
                        'unlimited': network.interstitial_daily_limit == 0
                    }
                    
                    # Only generate unique_id if limit not reached
                    if not limit_reached:
                        tracking_token = await create_tracking_token(
                            db_session, network, 'interstitial', network.interstitial_id,
                            android_id, user_ip, location
                        )
                        ad_data['unique_id'] = tracking_token
                    
                    interstitial_ads.append(ad_data)
            
            await db_session.commit()
            
            if not interstitial_ads:
                return jsonify({
                    'status': 'error',
                    'message': 'No interstitial ads available'
                }), 404
            
            return jsonify({
                'status': 'success',
                'type': 'interstitial',
                'total': len(interstitial_ads),
                'ads': interstitial_ads,
                'tracking_id': android_id if android_id else user_ip,
                'country': location['country_name'],
                'country_code': location['country_code'],
                'region': location['region']
            }), 200
        except Exception as e:
            await db_session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Failed to fetch interstitial ads: {str(e)}'
            }), 500

@bp.route('/rewarded_ads')
@require_api_token
async def get_rewarded_ads():
    android_id = request.args.get('android_id') or None
    user_ip = get_client_ip() if not android_id else None
    
    async with AsyncSessionLocal() as db_session:
        try:
            location = await get_request_location()
            
            result = await db_session.execute(
                select(AdNetwork)
                .where(AdNetwork.status == 'active')
                .order_by(AdNetwork.priority)
            )
            ad_networks = result.scalars().all()
            
            rewarded_ads = []
            for network in ad_networks:
                if network.rewarded_id:
                    play_count = await get_or_create_play_count(
                        db_session, network.id, 'rewarded', android_id, user_ip
                    )
                    
                    # Check if limit is reached
                    limit_reached = network.rewarded_daily_limit > 0 and play_count.play_count >= network.rewarded_daily_limit
                    
                    ad_data = {
                        'network_id': network.id,
                        'network_name': network.network_name,
                        'ad_type': 'rewarded',
                        'ad_unit_id': network.rewarded_id,
                        'priority': network.priority,
                        'daily_limit': network.rewarded_daily_limit,
                        'current_plays': play_count.play_count,
                        'remaining': max(0, network.rewarded_daily_limit - play_count.play_count) if network.rewarded_daily_limit > 0 else -1,
                        'limit_reached': limit_reached,
                        'unlimited': network.rewarded_daily_limit == 0
                    }
                    
                    # Only generate unique_id if limit not reached
                    if not limit_reached:
                        tracking_token = await create_tracking_token(
                            db_session, network, 'rewarded', network.rewarded_id,
                            android_id, user_ip, location
                        )
                        ad_data['unique_id'] = tracking_token
                    
                    rewarded_ads.append(ad_data)
            
            await db_session.commit()
            
            if not rewarded_ads:
                return jsonify({
                    'status': 'error',
                    'message': 'No rewarded ads available'
                }), 404
            
            return jsonify({
                'status': 'success',
                'type': 'rewarded',
                'total': len(rewarded_ads),
                'ads': rewarded_ads,
                'tracking_id': android_id if android_id else user_ip,
                'country': location['country_name'],
                'country_code': location['country_code'],
                'region': location['region']
            }), 200
        except Exception as e:
            await db_session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Failed to fetch rewarded ads: {str(e)}'
            }), 500

@bp.route('/all_ads')
@require_api_token
async def get_all_ads():
    """Get all ads with their IDs and priorities, sorted by priority"""
    android_id = request.args.get('android_id') or None
    user_ip = get_client_ip() if not android_id else None
    
    async with AsyncSessionLocal() as db_session:
        try:
            location = await get_request_location()
            
            result = await db_session.execute(
                select(AdNetwork)
                .where(AdNetwork.status == 'active')
                .order_by(AdNetwork.priority)
            )
            ad_networks = result.scalars().all()
            
            ads_list = []
            for network in ad_networks:
                ad_info = {
                    'network_id': network.id,
                    'network_name': network.network_name,
                    'priority': network.priority,
                    'status': network.status
                }
                
                # Add banner ad info if available
                if network.banner_id:
                    banner_data = {
                        'ad_id': network.banner_id,
                        'daily_limit': network.banner_daily_limit,
                        'unlimited': network.banner_daily_limit == 0
                    }
                    
                    if android_id or user_ip:
                        play_count = await get_or_create_play_count(
                            db_session, network.id, 'banner', android_id, user_ip
                        )
                        limit_reached = network.banner_daily_limit > 0 and play_count.play_count >= network.banner_daily_limit
                        banner_data['current_plays'] = play_count.play_count
                        banner_data['remaining'] = max(0, network.banner_daily_limit - play_count.play_count) if network.banner_daily_limit > 0 else -1
                        banner_data['limit_reached'] = limit_reached
                        
                        # Only generate unique_id if limit not reached
                        if not limit_reached:
                            tracking_token = await create_tracking_token(
                                db_session, network, 'banner', network.banner_id,
                                android_id, user_ip, location
                            )
                            banner_data['unique_id'] = tracking_token
                    
                    ad_info['banner'] = banner_data
                
                # Add interstitial ad info if available
                if network.interstitial_id:
                    interstitial_data = {
                        'ad_id': network.interstitial_id,
                        'daily_limit': network.interstitial_daily_limit,
                        'unlimited': network.interstitial_daily_limit == 0
                    }
                    
                    if android_id or user_ip:
                        play_count = await get_or_create_play_count(
                            db_session, network.id, 'interstitial', android_id, user_ip
                        )
                        limit_reached = network.interstitial_daily_limit > 0 and play_count.play_count >= network.interstitial_daily_limit
                        interstitial_data['current_plays'] = play_count.play_count
                        interstitial_data['remaining'] = max(0, network.interstitial_daily_limit - play_count.play_count) if network.interstitial_daily_limit > 0 else -1
                        interstitial_data['limit_reached'] = limit_reached
                        
                        # Only generate unique_id if limit not reached
                        if not limit_reached:
                            tracking_token = await create_tracking_token(
                                db_session, network, 'interstitial', network.interstitial_id,
                                android_id, user_ip, location
                            )
                            interstitial_data['unique_id'] = tracking_token
                    
                    ad_info['interstitial'] = interstitial_data
                
                # Add rewarded ad info if available
                if network.rewarded_id:
                    rewarded_data = {
                        'ad_id': network.rewarded_id,
                        'daily_limit': network.rewarded_daily_limit,
                        'unlimited': network.rewarded_daily_limit == 0
                    }
                    
                    if android_id or user_ip:
                        play_count = await get_or_create_play_count(
                            db_session, network.id, 'rewarded', android_id, user_ip
                        )
                        limit_reached = network.rewarded_daily_limit > 0 and play_count.play_count >= network.rewarded_daily_limit
                        rewarded_data['current_plays'] = play_count.play_count
                        rewarded_data['remaining'] = max(0, network.rewarded_daily_limit - play_count.play_count) if network.rewarded_daily_limit > 0 else -1
                        rewarded_data['limit_reached'] = limit_reached
                        
                        # Only generate unique_id if limit not reached
                        if not limit_reached:
                            tracking_token = await create_tracking_token(
                                db_session, network, 'rewarded', network.rewarded_id,
                                android_id, user_ip, location
                            )
                            rewarded_data['unique_id'] = tracking_token
                    
                    ad_info['rewarded'] = rewarded_data
                
                ads_list.append(ad_info)
            
            await db_session.commit()
            
            return jsonify({
                'status': 'success',
                'total_networks': len(ads_list),
                'ads': ads_list,
                'tracking_id': android_id if android_id else user_ip,
                'country': location['country_name'],
                'country_code': location['country_code'],
                'region': location['region']
            }), 200
        except Exception as e:
            await db_session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Failed to fetch all ads: {str(e)}'
            }), 500

@bp.route('/record_ad_play', methods=['POST'])
@require_api_token
async def record_ad_play():
    """Record that an ad was actually played using the unique_id and android_id"""
    data = await request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid request body'}), 400
    
    # Support both unique_id (new) and tracking_token (backward compatibility)
    unique_id = data.get('unique_id', '').strip() or data.get('tracking_token', '').strip()
    android_id = data.get('android_id', '').strip()
    
    if not unique_id:
        return jsonify({'status': 'error', 'message': 'unique_id is required'}), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            tracking_result = await db_session.execute(
                select(AdPlayTracking).where(
                    AdPlayTracking.tracking_token == unique_id
                ).with_for_update()
            )
            tracking_record = tracking_result.scalar_one_or_none()
            
            if not tracking_record:
                return jsonify({'status': 'error', 'message': 'Invalid unique_id'}), 404
            
            # If tracking record has android_id, require it in request and validate
            if tracking_record.android_id:
                if not android_id:
                    await db_session.rollback()
                    return jsonify({
                        'status': 'error',
                        'message': 'android_id is required for this unique_id'
                    }), 400
                if tracking_record.android_id != android_id:
                    await db_session.rollback()
                    return jsonify({
                        'status': 'error',
                        'message': 'android_id does not match the unique_id'
                    }), 400
            
            if tracking_record.is_played:
                await db_session.rollback()
                return jsonify({
                    'status': 'success',
                    'message': 'Ad play already recorded',
                    'network_name': tracking_record.network_name,
                    'ad_type': tracking_record.ad_type,
                    'played_at': tracking_record.played_at.isoformat() if tracking_record.played_at else None
                }), 200
            
            # Load ad network to check daily limit
            network_result = await db_session.execute(
                select(AdNetwork).where(AdNetwork.id == tracking_record.ad_network_id)
            )
            ad_network = network_result.scalar_one_or_none()
            
            if not ad_network:
                await db_session.rollback()
                return jsonify({'status': 'error', 'message': 'Ad network not found'}), 404
            
            # Get the daily limit for this ad type
            if tracking_record.ad_type == 'banner':
                daily_limit = ad_network.banner_daily_limit
            elif tracking_record.ad_type == 'interstitial':
                daily_limit = ad_network.interstitial_daily_limit
            else:  # rewarded
                daily_limit = ad_network.rewarded_daily_limit
            
            # Get current play count
            play_count = await get_or_create_play_count(
                db_session, tracking_record.ad_network_id, tracking_record.ad_type,
                tracking_record.android_id, tracking_record.user_ip
            )
            
            # Check if limit would be exceeded (0 means unlimited)
            if daily_limit > 0 and play_count.play_count >= daily_limit:
                await db_session.rollback()
                return jsonify({
                    'status': 'error',
                    'message': 'Daily limit reached for this ad network',
                    'network_name': tracking_record.network_name,
                    'ad_type': tracking_record.ad_type,
                    'daily_limit': daily_limit,
                    'current_plays': play_count.play_count
                }), 429
            
            # Record the play
            tracking_record.is_played = True
            tracking_record.played_at = datetime.now(timezone.utc)
            play_count.play_count += 1
            
            await db_session.commit()
            
            return jsonify({
                'status': 'success',
                'message': 'Ad play recorded successfully',
                'network_name': tracking_record.network_name,
                'ad_type': tracking_record.ad_type,
                'ad_unit_id': tracking_record.ad_unit_id,
                'android_id': tracking_record.android_id,
                'played_at': tracking_record.played_at.isoformat(),
                'new_play_count': play_count.play_count
            }), 200
        except Exception as e:
            await db_session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Failed to record ad play: {str(e)}'
            }), 500

@bp.route('/ad_limits')
@require_api_token
async def get_ad_limits():
    """Get current ad limit counts for a specific device/IP"""
    android_id = request.args.get('android_id') or None
    user_ip = get_client_ip() if not android_id else None
    token = request.args.get('token', '')
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(AdNetwork)
                .where(AdNetwork.status == 'active')
                .order_by(AdNetwork.priority)
            )
            ad_networks = result.scalars().all()
            
            ad_limits = []
            for network in ad_networks:
                network_data = {
                    'network_id': network.id,
                    'network_name': network.network_name,
                    'priority': network.priority,
                    'limits': {}
                }
                
                if network.banner_id:
                    play_count = await get_or_create_play_count(
                        db_session, network.id, 'banner', android_id, user_ip
                    )
                    network_data['limits']['banner'] = {
                        'daily_limit': network.banner_daily_limit,
                        'current_count': play_count.play_count,
                        'remaining': max(0, network.banner_daily_limit - play_count.play_count) if network.banner_daily_limit > 0 else -1,
                        'limit_reached': network.banner_daily_limit > 0 and play_count.play_count >= network.banner_daily_limit,
                        'unlimited': network.banner_daily_limit == 0,
                        'link': build_api_link('banner_ads', token, android_id)
                    }
                
                if network.interstitial_id:
                    play_count = await get_or_create_play_count(
                        db_session, network.id, 'interstitial', android_id, user_ip
                    )
                    network_data['limits']['interstitial'] = {
                        'daily_limit': network.interstitial_daily_limit,
                        'current_count': play_count.play_count,
                        'remaining': max(0, network.interstitial_daily_limit - play_count.play_count) if network.interstitial_daily_limit > 0 else -1,
                        'limit_reached': network.interstitial_daily_limit > 0 and play_count.play_count >= network.interstitial_daily_limit,
                        'unlimited': network.interstitial_daily_limit == 0,
                        'link': build_api_link('interstitial_ads', token, android_id)
                    }
                
                if network.rewarded_id:
                    play_count = await get_or_create_play_count(
                        db_session, network.id, 'rewarded', android_id, user_ip
                    )
                    network_data['limits']['rewarded'] = {
                        'daily_limit': network.rewarded_daily_limit,
                        'current_count': play_count.play_count,
                        'remaining': max(0, network.rewarded_daily_limit - play_count.play_count) if network.rewarded_daily_limit > 0 else -1,
                        'limit_reached': network.rewarded_daily_limit > 0 and play_count.play_count >= network.rewarded_daily_limit,
                        'unlimited': network.rewarded_daily_limit == 0,
                        'link': build_api_link('rewarded_ads', token, android_id)
                    }
                
                ad_limits.append(network_data)
            
            location = await get_request_location()
            
            return jsonify({
                'status': 'success',
                'tracking_id': android_id if android_id else user_ip,
                'total_networks': len(ad_limits),
                'networks': ad_limits,
                'country': location['country_name'],
                'country_code': location['country_code'],
                'region': location['region'],
                'api_links': {
                    'banner_ads': build_api_link('banner_ads', token, android_id),
                    'interstitial_ads': build_api_link('interstitial_ads', token, android_id),
                    'rewarded_ads': build_api_link('rewarded_ads', token, android_id),
                    'all_ads': build_api_link('all_ads', token, android_id),
                    'record_ad_play': build_api_link('record_ad_play', token),
                    'ad_limits': build_api_link('ad_limits', token, android_id)
                }
            }), 200
        except Exception as e:
            await db_session.rollback()
            return jsonify({
                'status': 'error',
                'message': f'Failed to fetch ad limits: {str(e)}'
            }), 500
