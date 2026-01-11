from quart import Blueprint, request, render_template, redirect, session
from bot.database import AsyncSessionLocal
from bot.models import Publisher, File, PublisherImpression, ImpressionAdjustment, PublisherRegistration, Settings
from bot.server.security import csrf_protect, get_csrf_token
from sqlalchemy import select, func, delete
from .utils import require_admin, hash_password
from datetime import datetime, timezone
from bot.modules.geoip import get_location_from_ip
from bot.server.referral_helper import create_referral_code_for_publisher
import logging

logger = logging.getLogger('bot.server')

def get_client_ip() -> str:
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    return request.remote_addr or '127.0.0.1'

def get_user_agent() -> str:
    return request.headers.get('User-Agent', 'Unknown')

bp = Blueprint('admin_publishers', __name__)

@bp.route('/register-publisher', methods=['POST'])
@require_admin
@csrf_protect
async def register_publisher():
    data = await request.form
    email = data.get('email', '').strip()
    password = data.get('password', '')
    traffic_source = data.get('traffic_source', '').strip()
    is_admin = data.get('is_admin') == 'on'
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).order_by(Publisher.created_at.desc())
        )
        publishers = result.scalars().all()
        
        publisher_files = {}
        publisher_impressions = {}
        publisher_adjustments = {}
        
        for publisher in publishers:
            file_count = await db_session.scalar(
                select(func.count(File.id)).where(File.publisher_id == publisher.id)
            )
            publisher_files[publisher.id] = file_count
            
            impression_count = await db_session.scalar(
                select(func.count(PublisherImpression.id)).where(PublisherImpression.publisher_id == publisher.id)
            )
            publisher_impressions[publisher.id] = impression_count or 0
            
            adjustment_total = await db_session.scalar(
                select(func.sum(ImpressionAdjustment.amount)).where(
                    ImpressionAdjustment.publisher_id == publisher.id,
                    ImpressionAdjustment.adjustment_type == 'add'
                )
            )
            publisher_adjustments[publisher.id] = int(adjustment_total) if adjustment_total else 0
        
        csrf_token = get_csrf_token()
        if not all([email, password, traffic_source]):
            return await render_template('admin_publishers.html', 
                                          active_page='publishers',
                                          publishers=publishers,
                                          publisher_files=publisher_files,
                                          publisher_impressions=publisher_impressions,
                                          publisher_adjustments=publisher_adjustments,
                                          error='All fields are required',
                                          csrf_token=csrf_token)
        
        try:
            result = await db_session.execute(
                select(Publisher).where(func.lower(Publisher.email) == email.lower())
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                return await render_template('admin_publishers.html', 
                                              active_page='publishers',
                                              publishers=publishers,
                                              publisher_files=publisher_files,
                                              publisher_impressions=publisher_impressions,
                                              publisher_adjustments=publisher_adjustments,
                                              error='Email already registered',
                                              csrf_token=csrf_token)
            
            password_hash = hash_password(password)
            
            publisher = Publisher(
                email=email,
                password_hash=password_hash,
                traffic_source=traffic_source,
                is_admin=is_admin,
                is_active=True
            )
            
            db_session.add(publisher)
            await db_session.commit()
            await db_session.refresh(publisher)
            
            client_ip = get_client_ip()
            user_agent = get_user_agent()
            country_code, country_name, region = await get_location_from_ip(client_ip)
            
            registration_log = PublisherRegistration(
                publisher_id=publisher.id,
                email=email,
                traffic_source=traffic_source,
                ip_address=client_ip,
                user_agent=user_agent,
                country_code=country_code,
                country_name=country_name
            )
            db_session.add(registration_log)
            await db_session.commit()
            
            await create_referral_code_for_publisher(publisher.id)
            
            return redirect('/admin/publishers')
            
        except Exception as e:
            await db_session.rollback()
            return await render_template('admin_publishers.html', 
                                          active_page='publishers',
                                          publishers=publishers,
                                          publisher_files=publisher_files,
                                          publisher_impressions=publisher_impressions,
                                          publisher_adjustments=publisher_adjustments,
                                          error='Registration failed',
                                          csrf_token=csrf_token)

@bp.route('/toggle-publisher/<int:publisher_id>', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_publisher(publisher_id):
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == publisher_id)
            )
            publisher = result.scalar_one_or_none()
            
            if publisher:
                publisher.is_active = not publisher.is_active
                await db_session.commit()
            
            return redirect('/admin/dashboard')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/dashboard')

@bp.route('/publishers')
@require_admin
async def publishers():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).order_by(Publisher.created_at.desc())
        )
        publishers = result.scalars().all()
        
        publisher_files = {}
        publisher_impressions = {}
        publisher_adjustments = {}
        
        for publisher in publishers:
            file_count = await db_session.scalar(
                select(func.count(File.id)).where(File.publisher_id == publisher.id)
            )
            publisher_files[publisher.id] = file_count
            
            impression_count = await db_session.scalar(
                select(func.count(PublisherImpression.id)).where(PublisherImpression.publisher_id == publisher.id)
            )
            publisher_impressions[publisher.id] = impression_count or 0
            
            adjustment_total = await db_session.scalar(
                select(func.sum(ImpressionAdjustment.amount)).where(
                    ImpressionAdjustment.publisher_id == publisher.id,
                    ImpressionAdjustment.adjustment_type == 'add'
                )
            )
            publisher_adjustments[publisher.id] = int(adjustment_total) if adjustment_total else 0
    
    csrf_token = get_csrf_token()
    return await render_template('admin_publishers.html', 
                                  active_page='publishers',
                                  publishers=publishers,
                                  publisher_files=publisher_files,
                                  publisher_impressions=publisher_impressions,
                                  publisher_adjustments=publisher_adjustments,
                                  csrf_token=csrf_token)

@bp.route('/publisher/<int:publisher_id>/files')
@require_admin
async def publisher_files(publisher_id):
    search_hash = request.args.get('search', '').strip()
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == publisher_id)
        )
        publisher = result.scalar_one_or_none()
        
        if not publisher:
            return redirect('/admin/publishers')
        
        query = select(File).where(File.publisher_id == publisher_id)
        
        if search_hash:
            query = query.where(File.access_code.ilike(f'%{search_hash}%'))
        
        query = query.order_by(File.created_at.desc())
        result = await db_session.execute(query)
        files = result.scalars().all()
        
    return await render_template('admin_publisher_files.html', 
                                  active_page='publishers',
                                  publisher=publisher,
                                  files=files,
                                  search_hash=search_hash)

@bp.route('/delete-file/<int:file_id>', methods=['POST'])
@require_admin
@csrf_protect
async def delete_file(file_id):
    publisher_id = request.args.get('publisher_id')
    
    async with AsyncSessionLocal() as db_session:
        try:
            stmt = delete(File).where(File.id == file_id)
            await db_session.execute(stmt)
            await db_session.commit()
            
            if publisher_id:
                return redirect(f'/admin/publisher/{publisher_id}/files')
            return redirect('/admin/publishers')
            
        except Exception as e:
            await db_session.rollback()
            if publisher_id:
                return redirect(f'/admin/publisher/{publisher_id}/files')
            return redirect('/admin/publishers')

@bp.route('/add-impressions/<int:publisher_id>', methods=['POST'])
@require_admin
@csrf_protect
async def add_impressions(publisher_id):
    data = await request.form
    amount_str = data.get('amount', '').strip()
    note = data.get('note', '').strip()
    
    try:
        amount = int(amount_str)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        return redirect('/admin/publishers')
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == publisher_id)
            )
            publisher = result.scalar_one_or_none()
            
            if not publisher:
                return redirect('/admin/publishers')
            
            # Get impression rate (use custom rate if set, otherwise global rate)
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            impression_rate = publisher.custom_impression_rate if publisher.custom_impression_rate is not None else (settings.impression_rate if settings else 0.0)
            
            # Calculate earnings and add to publisher balance
            earnings = amount * impression_rate
            publisher.balance += earnings
            
            admin_email = session.get('publisher_email', 'unknown')
            
            adjustment = ImpressionAdjustment(
                publisher_id=publisher_id,
                adjustment_type='add',
                amount=amount,
                note=note if note else None,
                admin_email=admin_email
            )
            
            db_session.add(adjustment)
            await db_session.commit()
            
            logger.info(f"Admin {admin_email} added {amount} impressions to publisher {publisher.email}, balance increased by ${earnings:.4f}")
            
            return redirect('/admin/publishers')
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error adding impressions: {e}")
            return redirect('/admin/publishers')

@bp.route('/set-custom-rate/<int:publisher_id>', methods=['POST'])
@require_admin
@csrf_protect
async def set_custom_rate(publisher_id):
    data = await request.form
    custom_rate_str = data.get('custom_rate', '').strip()
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == publisher_id)
            )
            publisher = result.scalar_one_or_none()
            
            if not publisher:
                return redirect('/admin/publishers')
            
            if custom_rate_str:
                try:
                    custom_rate = float(custom_rate_str)
                    if custom_rate < 0:
                        raise ValueError("Rate must be non-negative")
                    publisher.custom_impression_rate = custom_rate
                except ValueError:
                    return redirect('/admin/publishers')
            else:
                publisher.custom_impression_rate = None
            
            await db_session.commit()
            
            admin_email = session.get('publisher_email', 'unknown')
            logger.info(f"Admin {admin_email} set custom impression rate for publisher {publisher.email}: ${custom_rate_str or 'None'}")
            
            return redirect('/admin/publishers')
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error setting custom rate: {e}")
            return redirect('/admin/publishers')
