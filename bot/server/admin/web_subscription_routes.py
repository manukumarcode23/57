from quart import Blueprint, request, render_template, session, jsonify
from bot.database import AsyncSessionLocal
from bot.models import WebPublisherSubscription, WebPublisherSubscriptionPlan, Publisher, Settings
from sqlalchemy import select, desc, or_, and_
from .utils import require_admin
from bot.server.security import csrf_protect, get_csrf_token
from bot.server.payment_service import generate_order_id, create_payment_links, check_paytm_status, calculate_expiry_date
from logging import getLogger
from datetime import datetime

logger = getLogger('uvicorn')
bp = Blueprint('admin_web_subscription', __name__)


@bp.route('/web-subscriptions')
@require_admin
async def web_subscriptions():
    """Display admin web publisher subscriptions page"""
    async with AsyncSessionLocal() as db_session:
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        
        web_subscriptions_enabled = settings.web_publisher_subscriptions_enabled if settings else False
        
        result = await db_session.execute(
            select(WebPublisherSubscription, Publisher)
            .outerjoin(Publisher, WebPublisherSubscription.publisher_id == Publisher.id)
            .order_by(desc(WebPublisherSubscription.created_at))
        )
        subscriptions_data = result.all()
        
        plans_result = await db_session.execute(
            select(WebPublisherSubscriptionPlan)
            .order_by(WebPublisherSubscriptionPlan.amount)
        )
        plans = plans_result.scalars().all()
        
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        admin_user = result.scalar_one_or_none()
    
    csrf_token = get_csrf_token()
    return await render_template(
        'admin_web_subscriptions.html',
        active_page='web-subscriptions',
        subscriptions_data=subscriptions_data,
        plans=plans,
        web_subscriptions_enabled=web_subscriptions_enabled,
        admin_user=admin_user,
        csrf_token=csrf_token
    )


@bp.route('/web-subscriptions/toggle', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_web_subscriptions():
    """Toggle web publisher subscriptions on/off"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = Settings()
                db_session.add(settings)
            
            settings.web_publisher_subscriptions_enabled = not settings.web_publisher_subscriptions_enabled
            await db_session.commit()
            
            logger.info(f"Web Publisher Subscriptions {'enabled' if settings.web_publisher_subscriptions_enabled else 'disabled'} by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'enabled': settings.web_publisher_subscriptions_enabled,
                'message': f"Web Publisher Subscriptions {'enabled' if settings.web_publisher_subscriptions_enabled else 'disabled'} successfully"
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error toggling web subscriptions: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to update subscription settings'
            }), 500


@bp.route('/web-subscriptions/plans', methods=['GET'])
@require_admin
async def get_web_plans():
    """Get all web publisher subscription plans"""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(WebPublisherSubscriptionPlan).order_by(WebPublisherSubscriptionPlan.amount)
        )
        plans = result.scalars().all()
        
        return jsonify({
            'success': True,
            'plans': [{
                'id': plan.id,
                'name': plan.name,
                'amount': plan.amount,
                'duration_days': plan.duration_days,
                'upload_limit': plan.upload_limit,
                'max_file_size_mb': plan.max_file_size_mb,
                'description': plan.description,
                'is_active': plan.is_active
            } for plan in plans]
        }), 200


@bp.route('/web-subscriptions/plans/add', methods=['POST'])
@require_admin
@csrf_protect
async def add_web_plan():
    """Add a new web publisher subscription plan"""
    data = await request.form
    name = data.get('name', '').strip()
    amount = data.get('amount', '')
    duration_days = data.get('duration_days', '')
    upload_limit = data.get('upload_limit', '0')
    max_file_size_mb = data.get('max_file_size_mb', '2048')
    description = data.get('description', '').strip()
    
    if not name or not amount or not duration_days:
        return jsonify({
            'success': False,
            'message': 'Name, amount, and duration are required'
        }), 400
    
    try:
        amount = float(amount)
        duration_days = int(duration_days)
        upload_limit = int(upload_limit) if upload_limit else 0
        max_file_size_mb = int(max_file_size_mb) if max_file_size_mb else 2048
        
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
        
        if upload_limit < 0:
            return jsonify({
                'success': False,
                'message': 'Upload limit cannot be negative'
            }), 400
        
        if max_file_size_mb < 0:
            return jsonify({
                'success': False,
                'message': 'Max file size cannot be negative'
            }), 400
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid amount, duration, or limit format'
        }), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            plan = WebPublisherSubscriptionPlan(
                name=name,
                amount=amount,
                duration_days=duration_days,
                upload_limit=upload_limit,
                max_file_size_mb=max_file_size_mb,
                description=description if description else None,
                is_active=True
            )
            db_session.add(plan)
            await db_session.commit()
            
            logger.info(f"New web subscription plan added: {name} ({duration_days} days, max size: {max_file_size_mb}MB) by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'message': 'Web subscription plan added successfully',
                'plan': {
                    'id': plan.id,
                    'name': plan.name,
                    'amount': plan.amount,
                    'duration_days': plan.duration_days,
                    'upload_limit': plan.upload_limit,
                    'max_file_size_mb': plan.max_file_size_mb,
                    'description': plan.description
                }
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error adding web subscription plan: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to add web subscription plan'
            }), 500


@bp.route('/web-subscriptions/plans/<int:plan_id>/toggle', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_web_plan(plan_id):
    """Toggle a web subscription plan active/inactive"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(WebPublisherSubscriptionPlan).where(WebPublisherSubscriptionPlan.id == plan_id)
            )
            plan = result.scalar_one_or_none()
            
            if not plan:
                return jsonify({
                    'success': False,
                    'message': 'Plan not found'
                }), 404
            
            plan.is_active = not plan.is_active
            await db_session.commit()
            
            logger.info(f"Web subscription plan {plan.name} {'activated' if plan.is_active else 'deactivated'} by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'is_active': plan.is_active,
                'message': f"Plan {'activated' if plan.is_active else 'deactivated'} successfully"
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error toggling web subscription plan: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to toggle plan status'
            }), 500


@bp.route('/web-subscriptions/plans/<int:plan_id>/delete', methods=['POST'])
@require_admin
@csrf_protect
async def delete_web_plan(plan_id):
    """Delete a web subscription plan"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(WebPublisherSubscriptionPlan).where(WebPublisherSubscriptionPlan.id == plan_id)
            )
            plan = result.scalar_one_or_none()
            
            if not plan:
                return jsonify({
                    'success': False,
                    'message': 'Plan not found'
                }), 404
            
            await db_session.delete(plan)
            await db_session.commit()
            
            logger.info(f"Web subscription plan deleted: {plan.name} by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'message': 'Web subscription plan deleted successfully'
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error deleting web subscription plan: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to delete web subscription plan'
            }), 500


@bp.route('/web-subscriptions/grant', methods=['POST'])
@require_admin
@csrf_protect
async def grant_web_subscription():
    """Manually grant web subscription to a publisher"""
    data = await request.form
    publisher_email = data.get('publisher_email', '').strip()
    plan_id = data.get('plan_id', '')
    
    if not publisher_email:
        return jsonify({
            'success': False,
            'message': 'Publisher email is required'
        }), 400
    
    if not plan_id:
        return jsonify({
            'success': False,
            'message': 'Plan ID is required'
        }), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            publisher_result = await db_session.execute(
                select(Publisher).where(Publisher.email == publisher_email)
            )
            publisher = publisher_result.scalar_one_or_none()
            
            if not publisher:
                return jsonify({
                    'success': False,
                    'message': 'Publisher not found'
                }), 404
            
            plan_result = await db_session.execute(
                select(WebPublisherSubscriptionPlan).where(WebPublisherSubscriptionPlan.id == int(plan_id))
            )
            plan = plan_result.scalar_one_or_none()
            
            if not plan:
                return jsonify({
                    'success': False,
                    'message': 'Plan not found'
                }), 404
            
            order_id = generate_order_id()
            expires_at = calculate_expiry_date(plan.duration_days)
            
            subscription = WebPublisherSubscription(
                publisher_id=publisher.id,
                order_id=order_id,
                plan_id=plan.id,
                plan_name=plan.name,
                amount=plan.amount,
                duration_days=plan.duration_days,
                upload_limit=plan.upload_limit,
                max_file_size_mb=plan.max_file_size_mb,
                uploads_used=0,
                status='completed',
                payment_method='manual',
                utr_number='MANUAL_GRANT',
                expires_at=expires_at,
                paid_at=datetime.utcnow()
            )
            db_session.add(subscription)
            await db_session.commit()
            
            logger.info(f"Web subscription granted to {publisher_email} for plan {plan.name} by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'message': f'Web subscription granted to {publisher_email} successfully'
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error granting web subscription: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to grant subscription'
            }), 500


@bp.route('/web-subscriptions/<int:subscription_id>/extend', methods=['POST'])
@require_admin
@csrf_protect
async def extend_web_subscription(subscription_id):
    """Extend a web subscription by adding more days"""
    data = await request.form
    extend_days = data.get('extend_days', '')
    
    if not extend_days:
        return jsonify({
            'success': False,
            'message': 'Extension days are required'
        }), 400
    
    try:
        extend_days = int(extend_days)
        if extend_days <= 0:
            return jsonify({
                'success': False,
                'message': 'Extension days must be greater than 0'
            }), 400
    except ValueError:
        return jsonify({
            'success': False,
            'message': 'Invalid days format'
        }), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(WebPublisherSubscription).where(WebPublisherSubscription.id == subscription_id)
            )
            subscription = result.scalar_one_or_none()
            
            if not subscription:
                return jsonify({
                    'success': False,
                    'message': 'Subscription not found'
                }), 404
            
            from datetime import timedelta
            if subscription.expires_at:
                if subscription.expires_at > datetime.utcnow():
                    subscription.expires_at = subscription.expires_at + timedelta(days=extend_days)
                else:
                    subscription.expires_at = datetime.utcnow() + timedelta(days=extend_days)
                    subscription.status = 'completed'
            else:
                subscription.expires_at = datetime.utcnow() + timedelta(days=extend_days)
            
            subscription.duration_days += extend_days
            await db_session.commit()
            
            logger.info(f"Web subscription {subscription_id} extended by {extend_days} days by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'message': f'Subscription extended by {extend_days} days successfully',
                'new_expiry': subscription.expires_at.strftime('%Y-%m-%d') if subscription.expires_at else None
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error extending web subscription: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to extend subscription'
            }), 500


@bp.route('/web-subscriptions/<int:subscription_id>/cancel', methods=['POST'])
@require_admin
@csrf_protect
async def cancel_web_subscription(subscription_id):
    """Cancel/revoke a web subscription"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(WebPublisherSubscription).where(WebPublisherSubscription.id == subscription_id)
            )
            subscription = result.scalar_one_or_none()
            
            if not subscription:
                return jsonify({
                    'success': False,
                    'message': 'Subscription not found'
                }), 404
            
            subscription.status = 'cancelled'
            subscription.expires_at = datetime.utcnow()
            await db_session.commit()
            
            logger.info(f"Web subscription {subscription_id} cancelled by admin {session.get('publisher_email')}")
            
            return jsonify({
                'success': True,
                'message': 'Subscription cancelled successfully'
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error cancelling web subscription: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to cancel subscription'
            }), 500


@bp.route('/web-subscriptions/<int:subscription_id>/details', methods=['GET'])
@require_admin
async def get_subscription_details(subscription_id):
    """Get detailed information about a subscription"""
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(WebPublisherSubscription, Publisher)
                .outerjoin(Publisher, WebPublisherSubscription.publisher_id == Publisher.id)
                .where(WebPublisherSubscription.id == subscription_id)
            )
            row = result.first()
            
            if not row:
                return jsonify({
                    'success': False,
                    'message': 'Subscription not found'
                }), 404
            
            subscription, publisher = row
            
            return jsonify({
                'success': True,
                'subscription': {
                    'id': subscription.id,
                    'publisher_email': publisher.email if publisher else 'N/A',
                    'plan_name': subscription.plan_name,
                    'amount': subscription.amount,
                    'duration_days': subscription.duration_days,
                    'status': subscription.status,
                    'payment_method': subscription.payment_method,
                    'order_id': subscription.order_id,
                    'utr_number': subscription.utr_number,
                    'expires_at': subscription.expires_at.strftime('%Y-%m-%d %H:%M') if subscription.expires_at else None,
                    'created_at': subscription.created_at.strftime('%Y-%m-%d %H:%M') if subscription.created_at else None,
                    'paid_at': subscription.paid_at.strftime('%Y-%m-%d %H:%M') if subscription.paid_at else None
                }
            }), 200
            
        except Exception as e:
            logger.error(f"Error getting subscription details: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Failed to get subscription details'
            }), 500


@bp.route('/web-payments')
@require_admin
async def web_payments():
    """Display all web subscription payment transactions"""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(WebPublisherSubscription, Publisher)
            .outerjoin(Publisher, WebPublisherSubscription.publisher_id == Publisher.id)
            .order_by(desc(WebPublisherSubscription.created_at))
        )
        payment_data = result.all()
        
        plans_result = await db_session.execute(
            select(WebPublisherSubscriptionPlan)
            .where(WebPublisherSubscriptionPlan.is_active == True)
            .order_by(WebPublisherSubscriptionPlan.amount)
        )
        plans = plans_result.scalars().all()
        
        publishers_result = await db_session.execute(
            select(Publisher)
            .where(Publisher.is_active == True)
            .order_by(Publisher.email)
        )
        publishers = publishers_result.scalars().all()
        
        admin_user = None
        publisher_id = session.get('publisher_id')
        if publisher_id:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == publisher_id)
            )
            admin_user = result.scalar_one_or_none()
    
    csrf_token = get_csrf_token()
    return await render_template(
        'admin_web_payments.html',
        active_page='web-payments',
        payment_data=payment_data,
        plans=plans,
        publishers=publishers,
        admin_user=admin_user,
        csrf_token=csrf_token
    )


@bp.route('/web-payments/search', methods=['POST'])
@require_admin
@csrf_protect
async def search_web_payments():
    """Search web payments by Order ID or Publisher Email"""
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
                select(WebPublisherSubscription, Publisher)
                .outerjoin(Publisher, WebPublisherSubscription.publisher_id == Publisher.id)
                .where(
                    or_(
                        WebPublisherSubscription.order_id.ilike(f'%{search_query}%'),
                        Publisher.email.ilike(f'%{search_query}%')
                    )
                )
                .order_by(desc(WebPublisherSubscription.created_at))
                .limit(50)
            )
            payment_data = result.all()
            
            payments = []
            for subscription, publisher in payment_data:
                payments.append({
                    'id': subscription.id,
                    'order_id': subscription.order_id,
                    'publisher_email': publisher.email if publisher else None,
                    'plan_name': subscription.plan_name,
                    'amount': subscription.amount,
                    'upload_limit': subscription.upload_limit,
                    'uploads_used': subscription.uploads_used,
                    'status': subscription.status,
                    'payment_method': subscription.payment_method,
                    'utr_number': subscription.utr_number,
                    'created_at': subscription.created_at.strftime('%Y-%m-%d %H:%M') if subscription.created_at else None,
                    'expires_at': subscription.expires_at.strftime('%Y-%m-%d %H:%M') if subscription.expires_at else None
                })
            
            return jsonify({
                'success': True,
                'payments': payments
            }), 200
            
        except Exception as e:
            logger.error(f"Error searching web payments: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while searching payments'
            }), 500
