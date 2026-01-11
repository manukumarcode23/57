from quart import Blueprint, request, jsonify
from bot.database import AsyncSessionLocal
from bot.models import Subscription, Settings, SubscriptionPlan
from bot.server.api_auth import require_endpoint_api_key
from sqlalchemy import select, and_, or_, desc
from logging import getLogger
from datetime import datetime, timedelta
from os import environ
import string
import secrets
import httpx
import json
import urllib.parse

logger = getLogger('uvicorn')
bp = Blueprint('payment_api', __name__)

def generate_order_id(length=20):
    """Generate a random order ID"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))

async def check_android_subscription(android_id: str) -> dict:
    """
    Check if android_id has an active subscription
    Returns: {"has_subscription": bool, "subscription": dict or None}
    """
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Subscription).where(
                and_(
                    Subscription.android_id == android_id,
                    Subscription.status == 'completed',
                    or_(
                        Subscription.expires_at.is_(None),
                        Subscription.expires_at > datetime.utcnow()
                    )
                )
            ).order_by(desc(Subscription.expires_at))
        )
        subscription = result.scalars().first()
        
        if subscription:
            days_remaining = None
            if subscription.expires_at:
                delta = subscription.expires_at - datetime.utcnow()
                days_remaining = max(0, delta.days)
            
            return {
                "has_subscription": True,
                "subscription": {
                    "plan_name": subscription.plan_name,
                    "amount": subscription.amount,
                    "duration_days": subscription.duration_days,
                    "status": subscription.status,
                    "order_id": subscription.order_id,
                    "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
                    "paid_at": subscription.paid_at.isoformat() if subscription.paid_at else None,
                    "days_remaining": days_remaining
                }
            }
        
        return {"has_subscription": False, "subscription": None}

@bp.route('/api/payment/create-qr', methods=['POST'])
@require_endpoint_api_key('Payment API')
async def create_payment_qr():
    """
    Create QR code for payment using android_id
    
    Request Body:
    {
        "plan_id": int (required),
        "android_id": string (required)
    }
    
    Response:
    {
        "success": true,
        "order_id": "ABC123...",
        "amount": 99.0,
        "plan_name": "Basic Plan",
        "duration_days": 30,
        "upi_link": "upi://pay?...",
        "qr_url": "https://api.qrserver.com/...",
        "paytm_intent": "paytmmp://cash_wallet?...",
        "upi_id": "merchant@paytm",
        "created_at": "2024-01-01T00:00:00Z"
    }
    """
    try:
        data = await request.get_json()
        plan_id = data.get('plan_id')
        android_id = data.get('android_id', '').strip()
        
        if not plan_id:
            return jsonify({
                'success': False,
                'message': 'Plan ID is required'
            }), 400
        
        if not android_id:
            return jsonify({
                'success': False,
                'message': 'android_id is required'
            }), 400
        
        async with AsyncSessionLocal() as db_session:
            # Check if subscriptions are enabled
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            
            if not settings or not settings.subscriptions_enabled:
                return jsonify({
                    'success': False,
                    'message': 'Subscriptions are currently disabled'
                }), 400
            
            # Get the subscription plan
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
            
            # Generate unique order ID
            order_id = generate_order_id()
            
            # Create subscription record with android_id
            subscription = Subscription(
                android_id=android_id,
                publisher_id=None,
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
            
            # Get Paytm credentials from database settings first, fallback to environment variables
            upi_id = settings.paytm_upi_id or environ.get('PAYTM_UPI_ID')
            payee_name = settings.paytm_unit_id or environ.get('PAYTM_UNIT_ID')
            paytm_signature = settings.paytm_signature or environ.get('PAYTM_SIGNATURE')
            
            if not all([upi_id, payee_name]):
                logger.error("Missing required Paytm environment variables")
                return jsonify({
                    'success': False,
                    'message': 'Payment gateway not configured'
                }), 500
            
            # Build UPI payment link
            upi_link = f"upi://pay?pa={upi_id}&am={plan.amount}&pn={payee_name}&tn={order_id}&tr={order_id}"
            
            # Generate QR code URL
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&ecc=H&margin=20&data={urllib.parse.quote(upi_link)}"
            
            # Build Paytm intent link
            if paytm_signature:
                paytm_intent = f"paytmmp://cash_wallet?pa={upi_id}&pn={payee_name}&am={plan.amount}&cu=INR&tn={order_id}&tr={order_id}&mc=4722&sign={paytm_signature}&featuretype=money_transfer"
            else:
                paytm_intent = f"paytmmp://cash_wallet?pa={upi_id}&pn={payee_name}&am={plan.amount}&cu=INR&tn={order_id}&tr={order_id}&mc=4722&featuretype=money_transfer"
            
            logger.info(f"Payment QR created: Order {order_id} for Android ID {android_id}, Plan: {plan.name}, Amount: ₹{plan.amount}")
            
            created_at = subscription.created_at.isoformat() if subscription.created_at else datetime.utcnow().isoformat()
            
            # Simplified payment page URL - only order_id needed (server will fetch rest from database)
            payment_page_url = f"/payment-link?order_id={order_id}"
            
            return jsonify({
                'success': True,
                'order_id': order_id,
                'amount': plan.amount,
                'plan_name': plan.name,
                'duration_days': plan.duration_days,
                'upi_link': upi_link,
                'qr_url': qr_url,
                'paytm_intent': paytm_intent,
                'upi_id': upi_id,
                'payee_name': payee_name,
                'created_at': created_at,
                'payment_page_url': payment_page_url
            }), 200
            
    except Exception as e:
        logger.error(f"Error creating payment QR: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while creating payment QR'
        }), 500

@bp.route('/api/payment/check-status', methods=['GET', 'POST'])
@require_endpoint_api_key('Payment API')
async def check_payment_status():
    """
    Check payment status from Paytm
    
    Query Params (GET) or Body (POST):
    {
        "order_id": "ABC123..." (required)
    }
    
    Response:
    {
        "success": true,
        "status": "TXN_SUCCESS" | "TXN_FAILURE" | "PENDING",
        "order_id": "ABC123...",
        "txn_amount": "99.00",
        "bank_txn_id": "123456789",
        "message": "Payment successful!",
        "subscription": {
            "plan_name": "Basic Plan",
            "duration_days": 30,
            "expires_at": "2024-02-01T00:00:00Z",
            "paid_at": "2024-01-01T00:00:00Z"
        }
    }
    """
    order_id = None
    try:
        if request.method == 'POST':
            data = await request.get_json()
            order_id = data.get('order_id')
        else:
            order_id = request.args.get('order_id')
        
        if not order_id:
            return jsonify({
                'success': False,
                'message': 'Order ID is required'
            }), 400
        
        # Get Paytm MID from database settings first, fallback to environment variable
        async with AsyncSessionLocal() as db_session:
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            
            mid = (settings.paytm_mid if settings and settings.paytm_mid else None) or environ.get('PAYTM_MID')
            
            if not mid:
                logger.error("Missing PAYTM_MID in settings and environment variables")
                return jsonify({
                    'success': False,
                    'message': 'Payment verification not configured'
                }), 500
            
            # Build Paytm status check URL
            payload = json.dumps({'MID': mid, 'ORDERID': order_id})
            check_url = f"https://securegw.paytm.in/order/status?JsonData={urllib.parse.quote(payload)}"
        
        # Query Paytm API for payment status
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                check_url,
                headers={"Content-Type": "application/json"}
            )
            response_data = response.json()
            
            status = response_data.get('STATUS', 'PENDING')
            txn_amount = response_data.get('TXNAMOUNT', '')
            bank_txn_id = response_data.get('BANKTXNID', '')
            
            logger.info(f"Payment status check: Order {order_id}, Status: {status}")
        
        # Update subscription in database
        subscription_data = None
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(Subscription).where(Subscription.order_id == order_id)
            )
            subscription = result.scalar_one_or_none()
            
            if subscription and status == 'TXN_SUCCESS' and subscription.status == 'pending':
                subscription.status = 'completed'
                subscription.utr_number = bank_txn_id
                subscription.paid_at = datetime.utcnow()
                subscription.expires_at = datetime.utcnow() + timedelta(days=subscription.duration_days)
                await db_session.commit()
                
                logger.info(f"Payment completed: Order {order_id}, Android ID: {subscription.android_id}, Amount: ₹{txn_amount}, UTR: {bank_txn_id}")
                
                # Prepare subscription data for response
                subscription_data = {
                    'android_id': subscription.android_id,
                    'plan_name': subscription.plan_name,
                    'amount': subscription.amount,
                    'duration_days': subscription.duration_days,
                    'expires_at': subscription.expires_at.isoformat() if subscription.expires_at else None,
                    'paid_at': subscription.paid_at.isoformat() if subscription.paid_at else None
                }
            
            elif subscription and status == 'TXN_FAILURE':
                subscription.status = 'failed'
                await db_session.commit()
            
            elif subscription and subscription.status == 'completed':
                # Already completed, return subscription data
                subscription_data = {
                    'android_id': subscription.android_id,
                    'plan_name': subscription.plan_name,
                    'amount': subscription.amount,
                    'duration_days': subscription.duration_days,
                    'expires_at': subscription.expires_at.isoformat() if subscription.expires_at else None,
                    'paid_at': subscription.paid_at.isoformat() if subscription.paid_at else None
                }
        
        # Build response message
        message = 'Payment successful!' if status == 'TXN_SUCCESS' else \
                 'Payment failed' if status == 'TXN_FAILURE' else \
                 'Payment is pending'
        
        response_json = {
            'success': True,
            'status': status,
            'order_id': order_id,
            'txn_amount': txn_amount,
            'bank_txn_id': bank_txn_id,
            'message': message
        }
        
        # Add subscription data if available
        if subscription_data:
            response_json['subscription'] = subscription_data
        
        return jsonify(response_json), 200
            
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
            'message': f'An error occurred: {str(e)}'
        }), 500

@bp.route('/api/payment/plans', methods=['GET'])
@require_endpoint_api_key('Payment API')
async def get_payment_plans():
    """
    Get all active subscription plans
    
    Response:
    {
        "success": true,
        "plans": [
            {
                "id": 1,
                "name": "Basic Plan",
                "amount": 99.0,
                "duration_days": 30,
                "description": "Basic monthly subscription"
            }
        ]
    }
    """
    try:
        async with AsyncSessionLocal() as db_session:
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            
            if not settings or not settings.subscriptions_enabled:
                return jsonify({
                    'success': False,
                    'message': 'Subscriptions are currently disabled'
                }), 400
            
            result = await db_session.execute(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.is_active == True
                ).order_by(SubscriptionPlan.amount)
            )
            plans = result.scalars().all()
            
            return jsonify({
                'success': True,
                'plans': [{
                    'id': plan.id,
                    'name': plan.name,
                    'amount': plan.amount,
                    'duration_days': plan.duration_days,
                    'description': plan.description
                } for plan in plans]
            }), 200
            
    except Exception as e:
        logger.error(f"Error fetching payment plans: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while fetching plans'
        }), 500

@bp.route('/api/payment/subscription-status', methods=['GET', 'POST'])
@require_endpoint_api_key('Payment API')
async def get_subscription_status():
    """
    Get current subscription status for android_id
    
    Request (GET or POST):
    {
        "android_id": "your_android_id" (required)
    }
    
    Response:
    {
        "success": true,
        "has_active_subscription": true,
        "subscription": {
            "plan_name": "Basic Plan",
            "amount": 99.0,
            "duration_days": 30,
            "status": "completed",
            "order_id": "ABC123XYZ456",
            "expires_at": "2024-02-01T00:00:00Z",
            "paid_at": "2024-01-01T00:00:00Z",
            "days_remaining": 25
        }
    }
    """
    try:
        if request.method == 'POST':
            data = await request.get_json()
            android_id = data.get('android_id', '').strip() if data else ''
        else:
            android_id = request.args.get('android_id', '').strip()
        
        if not android_id:
            return jsonify({
                'success': False,
                'message': 'android_id is required'
            }), 400
        
        result = await check_android_subscription(android_id)
        
        if result['has_subscription']:
            return jsonify({
                'success': True,
                'has_active_subscription': True,
                'subscription': result['subscription']
            }), 200
        else:
            return jsonify({
                'success': True,
                'has_active_subscription': False,
                'message': 'No active subscription found'
            }), 200
            
    except Exception as e:
        logger.error(f"Error fetching subscription status: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while fetching subscription status'
        }), 500

@bp.route('/api/payment/expire', methods=['POST'])
@require_endpoint_api_key('Payment API')
async def expire_payment():
    """
    Expire and delete a pending payment when timer runs out
    
    Request Body:
    {
        "order_id": "ABC123..." (required)
    }
    
    Response:
    {
        "success": true,
        "message": "Payment expired and removed"
    }
    """
    try:
        data = await request.get_json()
        order_id = data.get('order_id', '').strip() if data else ''
        
        if not order_id:
            return jsonify({
                'success': False,
                'message': 'order_id is required'
            }), 400
        
        async with AsyncSessionLocal() as db_session:
            # Find the subscription
            result = await db_session.execute(
                select(Subscription).where(Subscription.order_id == order_id)
            )
            subscription = result.scalar_one_or_none()
            
            if not subscription:
                return jsonify({
                    'success': False,
                    'message': 'Payment not found'
                }), 404
            
            # Only delete if still pending (not paid)
            if subscription.status == 'pending':
                await db_session.delete(subscription)
                await db_session.commit()
                logger.info(f"Expired and deleted pending payment: Order {order_id}")
                
                return jsonify({
                    'success': True,
                    'message': 'Payment expired and removed'
                }), 200
            else:
                return jsonify({
                    'success': True,
                    'message': f'Payment already {subscription.status}'
                }), 200
                
    except Exception as e:
        logger.error(f"Error expiring payment: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while expiring payment'
        }), 500
