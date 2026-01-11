from quart import Blueprint, request, render_template, redirect, session, jsonify
from bot.database import AsyncSessionLocal
from bot.models import Subscription, Publisher, SubscriptionPlan
from sqlalchemy import select, desc, or_
from sqlalchemy.orm import joinedload
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token
from logging import getLogger
from datetime import datetime, timedelta
import string
import secrets

logger = getLogger('uvicorn')
bp = Blueprint('admin_payment', __name__)

def generate_order_id(length=20):
    """Generate a random order ID"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

@bp.route('/payments')
@require_admin
async def payments():
    """Display all payment transactions"""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Subscription, Publisher)
            .outerjoin(Publisher, Subscription.publisher_id == Publisher.id)
            .order_by(desc(Subscription.created_at))
        )
        payment_data = result.all()
        
        plans_result = await db_session.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.amount)
        )
        plans = plans_result.scalars().all()
        
        admin_user = None
        publisher_id = session.get('publisher_id')
        if publisher_id:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == publisher_id)
            )
            admin_user = result.scalar_one_or_none()
    
    csrf_token = get_csrf_token()
    return await render_template(
        'admin_payments.html',
        active_page='payments',
        payment_data=payment_data,
        plans=plans,
        admin_user=admin_user,
        csrf_token=csrf_token
    )

@bp.route('/payments/grant', methods=['POST'])
@require_admin
@csrf_protect
async def grant_premium():
    """Manually grant premium access to an Android ID"""
    data = await request.form
    android_id = data.get('android_id', '').strip()
    plan_id = data.get('plan_id', '')
    publisher_email = data.get('publisher_email', '').strip()
    
    if not android_id:
        return jsonify({
            'success': False,
            'message': 'Android ID is required'
        }), 400
    
    if not plan_id:
        return jsonify({
            'success': False,
            'message': 'Plan is required'
        }), 400
    
    try:
        plan_id = int(plan_id)
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid plan ID'
        }), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            plan_result = await db_session.execute(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.id == plan_id,
                    SubscriptionPlan.is_active == True
                )
            )
            plan = plan_result.scalar_one_or_none()
            
            if not plan:
                return jsonify({
                    'success': False,
                    'message': 'Plan not found or inactive'
                }), 404
            
            publisher_id = None
            if publisher_email:
                publisher_result = await db_session.execute(
                    select(Publisher).where(Publisher.email == publisher_email)
                )
                publisher = publisher_result.scalar_one_or_none()
                if publisher:
                    publisher_id = publisher.id
            
            active_subscription_result = await db_session.execute(
                select(Subscription).where(
                    Subscription.android_id == android_id,
                    Subscription.status == 'completed',
                    Subscription.expires_at > datetime.utcnow()
                )
            )
            active_subscription = active_subscription_result.scalar_one_or_none()
            
            if active_subscription:
                expiry_str = active_subscription.expires_at.strftime("%Y-%m-%d %H:%M") if active_subscription.expires_at else 'N/A'
                return jsonify({
                    'success': False,
                    'message': f'Android ID already has an active subscription until {expiry_str}'
                }), 400
            
            order_id = generate_order_id()
            
            subscription = Subscription(
                publisher_id=publisher_id,
                android_id=android_id,
                order_id=order_id,
                plan_id=plan.id,
                plan_name=plan.name,
                amount=plan.amount,
                duration_days=plan.duration_days,
                status='completed',
                payment_method='manual',
                utr_number=f'MANUAL-{order_id[:10]}',
                paid_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=plan.duration_days)
            )
            db_session.add(subscription)
            await db_session.commit()
            
            logger.info(f"Manual premium access granted to Android ID {android_id} by admin {session.get('publisher_email')}")
            
            expires_str = subscription.expires_at.strftime('%Y-%m-%d %H:%M') if subscription.expires_at else 'N/A'
            return jsonify({
                'success': True,
                'message': f'Premium access granted successfully! Order ID: {order_id}',
                'order_id': order_id,
                'expires_at': expires_str
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error granting premium access: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while granting premium access'
            }), 500

@bp.route('/payments/search', methods=['POST'])
@require_admin
@csrf_protect
async def search_payments():
    """Search payments by Android ID or Order ID"""
    data = await request.json
    search_query = data.get('query', '').strip()
    
    if not search_query:
        return jsonify({
            'success': False,
            'message': 'Search query is required'
        }), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Subscription, Publisher)
                .outerjoin(Publisher, Subscription.publisher_id == Publisher.id)
                .where(
                    or_(
                        Subscription.android_id.ilike(f'%{search_query}%'),
                        Subscription.order_id.ilike(f'%{search_query}%')
                    )
                )
                .order_by(desc(Subscription.created_at))
                .limit(50)
            )
            payment_data = result.all()
            
            payments = []
            for subscription, publisher in payment_data:
                payments.append({
                    'order_id': subscription.order_id,
                    'android_id': subscription.android_id,
                    'publisher_email': publisher.email if publisher else None,
                    'plan_name': subscription.plan_name,
                    'amount': subscription.amount,
                    'status': subscription.status,
                    'payment_method': subscription.payment_method,
                    'utr_number': subscription.utr_number,
                    'created_at': subscription.created_at.strftime('%Y-%m-%d %H:%M'),
                    'expires_at': subscription.expires_at.strftime('%Y-%m-%d %H:%M') if subscription.expires_at else None
                })
            
            return jsonify({
                'success': True,
                'payments': payments
            }), 200
            
        except Exception as e:
            logger.error(f"Error searching payments: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while searching payments'
            }), 500
