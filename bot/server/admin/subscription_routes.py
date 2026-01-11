from quart import Blueprint, request, render_template, redirect, session, jsonify
from bot.database import AsyncSessionLocal
from bot.models import Subscription, Publisher, Settings, SubscriptionPlan
from sqlalchemy import select, desc
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token
from logging import getLogger
from datetime import datetime, timedelta
from os import environ
import string
import secrets
import httpx
import json
import urllib.parse

logger = getLogger('uvicorn')
bp = Blueprint('admin_subscription', __name__)

def generate_order_id(length=20):
    """Generate a random order ID"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

@bp.route('/subscriptions')
@require_admin
async def subscriptions():
    """Display admin subscriptions page"""
    async with AsyncSessionLocal() as db_session:
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        
        subscriptions_enabled = settings.subscriptions_enabled if settings else False
        
        result = await db_session.execute(
            select(Subscription)
            .where(Subscription.publisher_id == session['publisher_id'])
            .order_by(desc(Subscription.created_at))
        )
        subscriptions = result.scalars().all()
        
        plans_result = await db_session.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.amount)
        )
        plans = plans_result.scalars().all()
        
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        admin_user = result.scalar_one_or_none()
    
    csrf_token = get_csrf_token()
    return await render_template(
        'admin_subscriptions.html',
        active_page='subscriptions',
        subscriptions=subscriptions,
        plans=plans,
        subscriptions_enabled=subscriptions_enabled,
        admin_user=admin_user,
        csrf_token=csrf_token
    )

@bp.route('/subscriptions/toggle', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_subscriptions():
    """Toggle subscriptions on/off"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = Settings()
                db_session.add(settings)
            
            settings.subscriptions_enabled = not settings.subscriptions_enabled
            await db_session.commit()
            
            logger.info(f"Subscriptions {'enabled' if settings.subscriptions_enabled else 'disabled'} by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'enabled': settings.subscriptions_enabled,
                'message': f"Subscriptions {'enabled' if settings.subscriptions_enabled else 'disabled'} successfully"
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error toggling subscriptions: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to update subscription settings'
            }), 500

@bp.route('/subscriptions/plans', methods=['GET'])
@require_admin
async def get_plans():
    """Get all subscription plans"""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(SubscriptionPlan).order_by(SubscriptionPlan.amount)
        )
        plans = result.scalars().all()
        
        return jsonify({
            'success': True,
            'plans': [{
                'id': plan.id,
                'name': plan.name,
                'amount': plan.amount,
                'duration_days': plan.duration_days,
                'description': plan.description,
                'is_active': plan.is_active
            } for plan in plans]
        }), 200

@bp.route('/subscriptions/plans/add', methods=['POST'])
@require_admin
@csrf_protect
async def add_plan():
    """Add a new subscription plan"""
    data = await request.form
    name = data.get('name', '').strip()
    amount = data.get('amount', '')
    duration_days = data.get('duration_days', '')
    description = data.get('description', '').strip()
    earning_per_link = data.get('earning_per_link', '0')
    monthly_link_limit = data.get('monthly_link_limit', '0')
    
    if not name or not amount or not duration_days:
        return jsonify({
            'success': False,
            'message': 'Name, amount, and duration are required'
        }), 400
    
    try:
        amount = float(amount)
        duration_days = int(duration_days)
        earning_per_link = float(earning_per_link) if earning_per_link else 0.0
        monthly_link_limit = int(monthly_link_limit) if monthly_link_limit else 0
        
        if amount <= 0:
            return jsonify({
                'success': False,
                'message': 'Amount must be greater than 0'
            }), 400
            
        if duration_days <= 0:
            return jsonify({
                'success': False,
                'message': 'Duration must be greater than 0 days'
            }), 400
        
        if earning_per_link < 0:
            return jsonify({
                'success': False,
                'message': 'Earning per link cannot be negative'
            }), 400
        
        if monthly_link_limit < 0:
            return jsonify({
                'success': False,
                'message': 'Monthly link limit cannot be negative'
            }), 400
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid amount, duration, or earning format'
        }), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            plan = SubscriptionPlan(
                name=name,
                amount=amount,
                duration_days=duration_days,
                description=description if description else None,
                earning_per_link=earning_per_link,
                monthly_link_limit=monthly_link_limit,
                is_active=True
            )
            db_session.add(plan)
            await db_session.commit()
            
            logger.info(f"New subscription plan added: {name} (earning: {earning_per_link}/link, limit: {monthly_link_limit}/month) by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'message': 'Subscription plan added successfully',
                'plan': {
                    'id': plan.id,
                    'name': plan.name,
                    'amount': plan.amount,
                    'duration_days': plan.duration_days,
                    'description': plan.description,
                    'earning_per_link': plan.earning_per_link,
                    'monthly_link_limit': plan.monthly_link_limit
                }
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error adding subscription plan: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to add subscription plan'
            }), 500

@bp.route('/subscriptions/plans/<int:plan_id>/delete', methods=['POST'])
@require_admin
@csrf_protect
async def delete_plan(plan_id):
    """Delete a subscription plan"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
            )
            plan = result.scalar_one_or_none()
            
            if not plan:
                return jsonify({
                    'success': False,
                    'message': 'Plan not found'
                }), 404
            
            await db_session.delete(plan)
            await db_session.commit()
            
            logger.info(f"Subscription plan deleted: {plan.name} by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'message': 'Subscription plan deleted successfully'
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error deleting subscription plan: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to delete subscription plan'
            }), 500

@bp.route('/subscriptions/create-payment', methods=['POST'])
@require_admin
@csrf_protect
async def create_payment():
    """Create a new payment order"""
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
            
            if not settings or not settings.subscriptions_enabled:
                return jsonify({
                    'success': False,
                    'message': 'Subscriptions are currently disabled'
                }), 400
            
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
            
            order_id = generate_order_id()
            
            subscription = Subscription(
                publisher_id=session['publisher_id'],
                order_id=order_id,
                plan_id=plan.id,
                plan_name=plan.name,
                amount=plan.amount,
                duration_days=plan.duration_days,
                status='pending',
                payment_method='paytm'
            )
            db_session.add(subscription)
            await db_session.commit()
            
            upi_id = environ.get('PAYTM_UPI_ID')
            unit_id = environ.get('PAYTM_UNIT_ID')
            paytm_signature = environ.get('PAYTM_SIGNATURE')
            
            if not all([upi_id, unit_id, paytm_signature]):
                logger.error("Missing required Paytm environment variables")
                return jsonify({
                    'success': False,
                    'message': 'Payment gateway not configured. Please contact administrator.'
                }), 500
            
            upi_link = f"upi://pay?pa={upi_id}&am={plan.amount}&pn={unit_id}&tn={order_id}&tr={order_id}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&ecc=H&margin=20&data={urllib.parse.quote(upi_link)}"
            
            if paytm_signature:
                paytm_intent = f"paytmmp://cash_wallet?pa={upi_id}&pn={unit_id}&am={plan.amount}&cu=INR&tn={order_id}&tr={order_id}&mc=4722&sign={paytm_signature}&featuretype=money_transfer"
            else:
                paytm_intent = f"paytmmp://cash_wallet?pa={upi_id}&pn={unit_id}&am={plan.amount}&cu=INR&tn={order_id}&tr={order_id}&mc=4722&featuretype=money_transfer"
            
            mid = environ.get('PAYTM_MID')
            
            logger.info(f"Payment order created: {order_id} for plan {plan.name} by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'order_id': order_id,
                'qr_url': qr_url,
                'paytm_intent': paytm_intent,
                'upi_link': upi_link,
                'amount': plan.amount,
                'upi_id': upi_id,
                'mid': mid
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error creating payment order: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while creating payment order'
            }), 500

@bp.route('/subscriptions/check-status/<order_id>', methods=['GET'])
@require_admin
async def check_payment_status(order_id):
    """Check payment status from Paytm using the working code pattern"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(Subscription).where(
                    Subscription.order_id == order_id,
                    Subscription.publisher_id == session['publisher_id']
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
            
            mid = environ.get('PAYTM_MID')
            
            if not mid:
                logger.error("Missing PAYTM_MID environment variable")
                return jsonify({
                    'success': False,
                    'message': 'Payment verification not configured'
                }), 500
            
            payload = json.dumps({'MID': mid, 'ORDERID': order_id})
            check_url = f"https://securegw.paytm.in/order/status?JsonData={urllib.parse.quote(payload)}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    check_url,
                    headers={"Content-Type": "application/json"}
                )
                response_data = response.json()
                
                logger.info(f"Payment status check for {order_id}: STATUS={response_data.get('STATUS')}")
                
                status = response_data.get('STATUS', '')
                txn_amount = response_data.get('TXNAMOUNT', '')
                utr = response_data.get('BANKTXNID', '')
                
                if status == 'TXN_SUCCESS':
                    subscription.status = 'completed'
                    subscription.utr_number = utr
                    subscription.paid_at = datetime.utcnow()
                    subscription.expires_at = datetime.utcnow() + timedelta(days=subscription.duration_days)
                    
                    await db_session.commit()
                    
                    logger.info(f"Payment successful for order {order_id}, Amount: {txn_amount}, UTR: {utr}")
                    
                    return jsonify({
                        'success': True,
                        'status': 'completed',
                        'amount': txn_amount,
                        'utr': utr,
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
                    
        except httpx.TimeoutException:
            logger.error(f"Timeout while checking payment status for {order_id}")
            return jsonify({
                'success': False,
                'message': 'Payment status check timed out'
            }), 500
        except Exception as e:
            logger.error(f"Error checking payment status: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while checking payment status'
            }), 500
