from quart import Blueprint, render_template, request, jsonify
from sqlalchemy import select, func, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from bot.database import AsyncSessionLocal
from bot.models import Publisher, PublisherRegistration, PublisherLoginEvent, PublisherAccountLink
from bot.server.admin.utils import require_admin
from bot.modules.device_detection import generate_hardware_fingerprint
from bot.server.security import get_csrf_token
from datetime import datetime, timedelta, timezone
import ipaddress
import logging
import json

logger = logging.getLogger(__name__)

bp = Blueprint('admin_activity', __name__)

def mask_ip(ip: str) -> str:
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.version == 4:
            parts = ip.split('.')
            return f"{parts[0]}.{parts[1]}.{parts[2]}.***"
        else:
            parts = ip.split(':')
            return ':'.join(parts[:4]) + ':****'
    except ValueError:
        return "***.***.***"

@bp.route('/publisher-activity')
@require_admin
async def publisher_activity():
    try:
        days_filter = max(1, min(int(request.args.get('days', 7)), 365))
        reg_page = max(1, int(request.args.get('reg_page', 1)))
        login_page = max(1, int(request.args.get('login_page', 1)))
    except (ValueError, TypeError):
        days_filter = 7
        reg_page = 1
        login_page = 1
    
    page_size = 25
    since_date = datetime.now(timezone.utc) - timedelta(days=days_filter)
    
    try:
        async with AsyncSessionLocal() as db_session:
            total_registrations_count = await db_session.scalar(
                select(func.count(PublisherRegistration.id))
                .where(PublisherRegistration.created_at >= since_date)
            )
            
            reg_offset = (reg_page - 1) * page_size
            recent_registrations_result = await db_session.execute(
                select(PublisherRegistration, Publisher.email.label('current_email'))
                .join(Publisher, PublisherRegistration.publisher_id == Publisher.id)
                .where(PublisherRegistration.created_at >= since_date)
                .order_by(desc(PublisherRegistration.created_at))
                .limit(page_size)
                .offset(reg_offset)
            )
            recent_registrations = recent_registrations_result.all()
            
            total_logins_count = await db_session.scalar(
                select(func.count(PublisherLoginEvent.id))
                .where(PublisherLoginEvent.created_at >= since_date)
            )
            
            login_offset = (login_page - 1) * page_size
            recent_logins_result = await db_session.execute(
                select(PublisherLoginEvent)
                .where(PublisherLoginEvent.created_at >= since_date)
                .order_by(desc(PublisherLoginEvent.created_at))
                .limit(page_size)
                .offset(login_offset)
            )
            recent_logins = recent_logins_result.scalars().all()
            
            linked_accounts_result = await db_session.execute(
                select(
                    PublisherAccountLink.cluster_id,
                    func.count(func.distinct(PublisherAccountLink.publisher_id)).label('account_count'),
                    func.max(PublisherAccountLink.confidence).label('max_confidence'),
                    func.max(PublisherAccountLink.relationship_reason).label('primary_reason'),
                    func.max(PublisherAccountLink.created_at).label('latest_detection')
                )
                .where(PublisherAccountLink.created_at >= since_date)
                .where(PublisherAccountLink.confidence >= 0.7)
                .group_by(PublisherAccountLink.cluster_id)
                .having(func.count(func.distinct(PublisherAccountLink.publisher_id)) > 1)
                .order_by(desc('max_confidence'))
                .limit(20)
            )
            linked_clusters = linked_accounts_result.all()
            
            cluster_details = {}
            for cluster in linked_clusters:
                cluster_publishers_result = await db_session.execute(
                    select(Publisher.id, Publisher.email, Publisher.is_active, PublisherAccountLink.confidence)
                    .join(PublisherAccountLink, Publisher.id == PublisherAccountLink.publisher_id)
                    .where(PublisherAccountLink.cluster_id == cluster.cluster_id)
                    .distinct()
                )
                cluster_details[cluster.cluster_id] = cluster_publishers_result.all()
            
            total_logins = await db_session.scalar(
                select(func.count(PublisherLoginEvent.id))
                .where(PublisherLoginEvent.created_at >= since_date)
                .where(PublisherLoginEvent.success.is_(True))
            )
            
            failed_logins = await db_session.scalar(
                select(func.count(PublisherLoginEvent.id))
                .where(PublisherLoginEvent.created_at >= since_date)
                .where(PublisherLoginEvent.success.is_(False))
            )
            
            suspected_accounts = await db_session.scalar(
                select(func.count(func.distinct(PublisherAccountLink.publisher_id)))
                .where(PublisherAccountLink.created_at >= since_date)
                .where(PublisherAccountLink.confidence >= 0.7)
            )
            
            # Enhanced device-based duplicate account detection
            # Standard device fingerprint (includes IP)
            device_duplicates_result = await db_session.execute(
                select(
                    PublisherRegistration.device_fingerprint,
                    func.count(func.distinct(PublisherRegistration.publisher_id)).label('account_count'),
                    func.array_agg(func.distinct(PublisherRegistration.publisher_id)).label('publisher_ids'),
                    func.count(func.distinct(PublisherRegistration.ip_address)).label('ip_count')
                )
                .where(PublisherRegistration.created_at >= since_date)
                .where(PublisherRegistration.device_fingerprint.isnot(None))
                .where(PublisherRegistration.device_fingerprint != '')
                .group_by(PublisherRegistration.device_fingerprint)
                .having(func.count(func.distinct(PublisherRegistration.publisher_id)) > 1)
                .order_by(desc('account_count'))
                .limit(20)
            )
            device_duplicates = device_duplicates_result.all()
            
            # CRITICAL: Hardware fingerprint detection (same device across different IPs/networks)
            hardware_fingerprint_duplicates_result = await db_session.execute(
                select(
                    PublisherRegistration.hardware_fingerprint,
                    func.count(func.distinct(PublisherRegistration.publisher_id)).label('account_count'),
                    func.array_agg(func.distinct(PublisherRegistration.publisher_id)).label('publisher_ids'),
                    func.count(func.distinct(PublisherRegistration.ip_address)).label('ip_count')
                )
                .where(PublisherRegistration.created_at >= since_date)
                .where(PublisherRegistration.hardware_fingerprint.isnot(None))
                .where(PublisherRegistration.hardware_fingerprint != '')
                .group_by(PublisherRegistration.hardware_fingerprint)
                .having(func.count(func.distinct(PublisherRegistration.publisher_id)) > 1)
                .having(func.count(func.distinct(PublisherRegistration.ip_address)) > 1)  # Only show cross-IP matches
                .order_by(desc('account_count'))
                .limit(20)
            )
            hardware_fingerprint_duplicates = hardware_fingerprint_duplicates_result.all()
            
            # Get detailed info for each device fingerprint cluster
            device_cluster_details = {}
            for dup in device_duplicates:
                if dup.publisher_ids:
                    publishers_result = await db_session.execute(
                        select(
                            Publisher.id,
                            Publisher.email,
                            Publisher.is_active,
                            Publisher.balance,
                            PublisherRegistration.device_type,
                            PublisherRegistration.device_name,
                            PublisherRegistration.operating_system,
                            PublisherRegistration.browser_name,
                            PublisherRegistration.ip_address,
                            PublisherRegistration.created_at
                        )
                        .join(PublisherRegistration, Publisher.id == PublisherRegistration.publisher_id)
                        .where(PublisherRegistration.device_fingerprint == dup.device_fingerprint)
                        .where(PublisherRegistration.publisher_id.in_(dup.publisher_ids))
                        .order_by(PublisherRegistration.created_at)
                        .distinct()
                    )
                    device_cluster_details[dup.device_fingerprint] = publishers_result.all()
            
            # Get detailed info for each hardware fingerprint cluster (cross-IP detection)
            hardware_cluster_details = {}
            for dup in hardware_fingerprint_duplicates:
                if dup.publisher_ids:
                    publishers_result = await db_session.execute(
                        select(
                            Publisher.id,
                            Publisher.email,
                            Publisher.is_active,
                            Publisher.balance,
                            PublisherRegistration.device_type,
                            PublisherRegistration.device_name,
                            PublisherRegistration.operating_system,
                            PublisherRegistration.browser_name,
                            PublisherRegistration.ip_address,
                            PublisherRegistration.created_at
                        )
                        .join(PublisherRegistration, Publisher.id == PublisherRegistration.publisher_id)
                        .where(PublisherRegistration.hardware_fingerprint == dup.hardware_fingerprint)
                        .where(PublisherRegistration.publisher_id.in_(dup.publisher_ids))
                        .order_by(PublisherRegistration.created_at)
                        .distinct()
                    )
                    hardware_cluster_details[dup.hardware_fingerprint] = publishers_result.all()
            
            # Also check for similar hardware fingerprints (browsers with matching hardware profiles)
            hardware_duplicates_result = await db_session.execute(
                select(
                    func.count(func.distinct(PublisherRegistration.publisher_id)).label('account_count'),
                    func.array_agg(func.distinct(PublisherRegistration.publisher_id)).label('publisher_ids')
                )
                .where(PublisherRegistration.created_at >= since_date)
                .where(PublisherRegistration.device_type.isnot(None))
                .where(PublisherRegistration.device_name.isnot(None))
                .where(PublisherRegistration.operating_system.isnot(None))
                .group_by(
                    PublisherRegistration.device_type,
                    PublisherRegistration.device_name,
                    PublisherRegistration.operating_system,
                    PublisherRegistration.browser_name
                )
                .having(func.count(func.distinct(PublisherRegistration.publisher_id)) > 1)
                .order_by(desc('account_count'))
                .limit(10)
            )
            hardware_duplicates = hardware_duplicates_result.all()
            
            reg_total_pages = (total_registrations_count + page_size - 1) // page_size if total_registrations_count else 1
            login_total_pages = (total_logins_count + page_size - 1) // page_size if total_logins_count else 1
            
            csrf_token = get_csrf_token()
            
            return await render_template(
                'admin_publisher_activity.html',
                active_page='publisher_activity',
                recent_registrations=recent_registrations,
                recent_logins=recent_logins,
                linked_clusters=linked_clusters,
                cluster_details=cluster_details,
                device_duplicates=device_duplicates,
                device_cluster_details=device_cluster_details,
                hardware_duplicates=hardware_duplicates,
                hardware_fingerprint_duplicates=hardware_fingerprint_duplicates,
                hardware_cluster_details=hardware_cluster_details,
                total_registrations=total_registrations_count or 0,
                total_logins=total_logins or 0,
                failed_logins=failed_logins or 0,
                suspected_accounts=suspected_accounts or 0,
                days_filter=days_filter,
                reg_page=reg_page,
                login_page=login_page,
                reg_total_pages=reg_total_pages,
                login_total_pages=login_total_pages,
                page_size=page_size,
                mask_ip=mask_ip,
                csrf_token=csrf_token
            )
    except SQLAlchemyError as e:
        logger.error(f"Database error in publisher activity monitoring: {str(e)}")
        csrf_token = get_csrf_token()
        return await render_template(
            'admin_publisher_activity.html',
            active_page='publisher_activity',
            recent_registrations=[],
            recent_logins=[],
            linked_clusters=[],
            cluster_details={},
            device_duplicates=[],
            device_cluster_details={},
            hardware_duplicates=[],
            hardware_fingerprint_duplicates=[],
            hardware_cluster_details={},
            total_registrations=0,
            total_logins=0,
            failed_logins=0,
            suspected_accounts=0,
            days_filter=days_filter,
            reg_page=reg_page,
            login_page=login_page,
            reg_total_pages=1,
            login_total_pages=1,
            page_size=page_size,
            mask_ip=mask_ip,
            csrf_token=csrf_token,
            error_message="An error occurred while loading activity data. Please try again later."
        )
    except Exception as e:
        logger.error(f"Unexpected error in publisher activity monitoring: {str(e)}")
        csrf_token = get_csrf_token()
        return await render_template(
            'admin_publisher_activity.html',
            active_page='publisher_activity',
            recent_registrations=[],
            recent_logins=[],
            linked_clusters=[],
            cluster_details={},
            device_duplicates=[],
            device_cluster_details={},
            hardware_duplicates=[],
            hardware_fingerprint_duplicates=[],
            hardware_cluster_details={},
            total_registrations=0,
            total_logins=0,
            failed_logins=0,
            suspected_accounts=0,
            days_filter=days_filter,
            reg_page=reg_page,
            login_page=login_page,
            reg_total_pages=1,
            login_total_pages=1,
            page_size=page_size,
            mask_ip=mask_ip,
            csrf_token=csrf_token,
            error_message="An unexpected error occurred. Please try again later."
        )
