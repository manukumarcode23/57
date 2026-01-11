from quart import Blueprint, request, render_template, session, jsonify
from bot.database import AsyncSessionLocal
from bot.models import WebPublisherSubscription, WebPublisherSubscriptionPlan, Publisher, Settings
from sqlalchemy import select, desc, and_, or_
from .utils import require_publisher
from bot.server.security import csrf_protect, get_csrf_token
from bot.server.payment_service import generate_order_id, create_payment_links, check_paytm_status, calculate_expiry_date
from logging import getLogger
from datetime import datetime

logger = getLogger('uvicorn')
bp = Blueprint('publisher_subscription', __name__)


async def get_active_web_subscription(publisher_id: int):
    """Get active web subscription for a publisher"""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(WebPublisherSubscription).where(
                and_(
                    WebPublisherSubscription.publisher_id == publisher_id,
                    WebPublisherSubscription.status == 'completed',
                    or_(
                        WebPublisherSubscription.expires_at.is_(None),
                        WebPublisherSubscription.expires_at > datetime.utcnow()
                    )
                )
            ).order_by(desc(WebPublisherSubscription.expires_at))
        )
        return result.scalar_one_or_none()


async def check_upload_allowed(publisher_id: int):
    """
    Check if publisher is allowed to upload based on web subscription.
    Monthly-based subscription - unlimited uploads during active subscription period.
    Returns: (allowed: bool, subscription: WebPublisherSubscription or None, message: str)
    """
    async with AsyncSessionLocal() as db_session:
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        
        if not settings or not settings.web_publisher_subscriptions_enabled:
            return True, None, "Subscriptions not required"
        
        subscription = await get_active_web_subscription(publisher_id)
        
        if not subscription:
            return False, None, "Active subscription required to upload videos"
        
        return True, subscription, "Upload allowed"


@bp.route('/subscription')
@require_publisher
async def subscription():
    """Display publisher subscription page"""
    async with AsyncSessionLocal() as db_session:
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        
        web_subscriptions_enabled = settings.web_publisher_subscriptions_enabled if settings else False
        
        active_subscription = await get_active_web_subscription(session['publisher_id'])
        
        result = await db_session.execute(
            select(WebPublisherSubscription)
            .where(WebPublisherSubscription.publisher_id == session['publisher_id'])
            .order_by(desc(WebPublisherSubscription.created_at))
        )
        subscriptions = result.scalars().all()
        
        plans_result = await db_session.execute(
            select(WebPublisherSubscriptionPlan)
            .where(WebPublisherSubscriptionPlan.is_active == True)
            .order_by(WebPublisherSubscriptionPlan.amount)
        )
        plans = plans_result.scalars().all()
    
    csrf_token = get_csrf_token()
    return await render_template(
        'publisher_subscription.html',
        active_page='subscription',
        email=session['publisher_email'],
        web_subscriptions_enabled=web_subscriptions_enabled,
        active_subscription=active_subscription,
        subscriptions=subscriptions,
        plans=plans,
        csrf_token=csrf_token
    )


@bp.route('/subscription/create-payment', methods=['POST'])
@require_publisher
@csrf_protect
async def create_payment():
    """Create a new payment order for web subscription"""
    data = await request.form
    plan_id = data.get('plan_id', '')
    
    if not plan_id:
        return jsonify({
            'success': False,
            'message': 'Plan ID is required'
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
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            
            if not settings or not settings.web_publisher_subscriptions_enabled:
                return jsonify({
                    'success': False,
                    'message': 'Web subscriptions are currently disabled'
                }), 400
            
            plan_result = await db_session.execute(
                select(WebPublisherSubscriptionPlan).where(
                    WebPublisherSubscriptionPlan.id == plan_id,
                    WebPublisherSubscriptionPlan.is_active == True
                )
            )
            plan = plan_result.scalar_one_or_none()
            
            if not plan:
                return jsonify({
                    'success': False,
                    'message': 'Plan not found or inactive'
                }), 404
            
            order_id = generate_order_id()
            
            subscription = WebPublisherSubscription(
                publisher_id=session['publisher_id'],
                order_id=order_id,
                plan_id=plan.id,
                plan_name=plan.name,
                amount=plan.amount,
                duration_days=plan.duration_days,
                upload_limit=plan.upload_limit,
                max_file_size_mb=plan.max_file_size_mb,
                uploads_used=0,
                status='pending',
                payment_method='paytm'
            )
            db_session.add(subscription)
            await db_session.commit()
            
            payment_links = await create_payment_links(plan.amount, order_id)
            
            if not payment_links['success']:
                return jsonify({
                    'success': False,
                    'message': payment_links.get('error', 'Payment gateway not configured')
                }), 500
            
            logger.info(f"Web subscription payment order created: {order_id} for plan {plan.name} by publisher {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'order_id': order_id,
                'qr_url': payment_links['qr_url'],
                'paytm_intent': payment_links['paytm_intent'],
                'upi_link': payment_links['upi_link'],
                'amount': plan.amount,
                'upi_id': payment_links['upi_id']
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error creating web subscription payment order: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while creating payment order'
            }), 500


@bp.route('/subscription/check-status/<order_id>', methods=['GET'])
@require_publisher
async def check_payment_status(order_id):
    """Check payment status for web subscription"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(WebPublisherSubscription).where(
                    WebPublisherSubscription.order_id == order_id,
                    WebPublisherSubscription.publisher_id == session['publisher_id']
                )
            )
            subscription = result.scalar_one_or_none()
            
            if not subscription:
                return jsonify({
                    'success': False,
                    'message': 'Subscription not found'
                }), 404
            
            if subscription.status == 'completed':
                return jsonify({
                    'success': True,
                    'status': 'completed',
                    'message': 'Payment already completed'
                }), 200
            
            paytm_result = await check_paytm_status(order_id)
            
            if not paytm_result['success']:
                return jsonify({
                    'success': False,
                    'message': paytm_result.get('error', 'Payment check failed')
                }), 500
            
            status = paytm_result['status']
            
            if status == 'TXN_SUCCESS':
                subscription.status = 'completed'
                subscription.utr_number = paytm_result.get('utr', '')
                subscription.paid_at = datetime.utcnow()
                subscription.expires_at = calculate_expiry_date(subscription.duration_days)
                
                await db_session.commit()
                
                logger.info(f"Web subscription payment successful for order {order_id}, UTR: {paytm_result.get('utr')}")
                
                return jsonify({
                    'success': True,
                    'status': 'completed',
                    'amount': paytm_result.get('amount'),
                    'utr': paytm_result.get('utr'),
                    'message': 'Payment successful!'
                }), 200
            elif status == 'TXN_FAILURE':
                subscription.status = 'failed'
                await db_session.commit()
                
                return jsonify({
                    'success': False,
                    'status': 'failed',
                    'message': 'Payment failed. Please try again.'
                }), 200
            else:
                return jsonify({
                    'success': True,
                    'status': 'pending',
                    'message': 'Payment is still pending'
                }), 200
                    
        except Exception as e:
            logger.error(f"Error checking web subscription payment status: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while checking payment status'
            }), 500
