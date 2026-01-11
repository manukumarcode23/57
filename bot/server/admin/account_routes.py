from quart import Blueprint, request, render_template, redirect, session, jsonify
from bot.database import AsyncSessionLocal
from bot.models import Publisher
from sqlalchemy import select
from .utils import require_admin, hash_password
from bot.server.security import csrf_protect, get_csrf_token
import bcrypt
from logging import getLogger

logger = getLogger('uvicorn')
bp = Blueprint('admin_account', __name__)

@bp.route('/account')
@require_admin
async def account_settings():
    """Display admin account settings page"""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        admin_user = result.scalar_one_or_none()
        
        if not admin_user:
            return redirect('/login')
    
    csrf_token = get_csrf_token()
    return await render_template(
        'admin_account.html', 
        active_page='account',
        admin_user=admin_user,
        csrf_token=csrf_token
    )

@bp.route('/account/update-email', methods=['POST'])
@require_admin
@csrf_protect
async def update_email():
    """Update admin email address"""
    data = await request.form
    new_email = data.get('new_email', '').strip().lower()
    current_password = data.get('current_password', '')
    
    if not new_email or not current_password:
        return jsonify({
            'success': False,
            'message': 'Email and password are required'
        }), 400
    
    # Validate email format
    if '@' not in new_email or '.' not in new_email:
        return jsonify({
            'success': False,
            'message': 'Invalid email format'
        }), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            # Get current admin user
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == session['publisher_id'])
            )
            admin_user = result.scalar_one_or_none()
            
            if not admin_user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404
            
            # Verify current password
            if not bcrypt.checkpw(current_password.encode('utf-8'), admin_user.password_hash.encode('utf-8')):
                logger.warning(f"Failed email change attempt for admin {admin_user.email} - incorrect password")
                return jsonify({
                    'success': False,
                    'message': 'Current password is incorrect'
                }), 401
            
            # Check if new email already exists
            existing_result = await db_session.execute(
                select(Publisher).where(
                    Publisher.email == new_email,
                    Publisher.id != admin_user.id
                )
            )
            existing_user = existing_result.scalar_one_or_none()
            
            if existing_user:
                return jsonify({
                    'success': False,
                    'message': 'Email address already in use'
                }), 400
            
            # Update email
            old_email = admin_user.email
            admin_user.email = new_email
            await db_session.commit()
            
            # Update session
            session['publisher_email'] = new_email
            
            logger.info(f"Admin email changed from {old_email} to {new_email}")
            
            return jsonify({
                'success': True,
                'message': 'Email updated successfully'
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error updating admin email: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while updating email'
            }), 500

@bp.route('/account/update-password', methods=['POST'])
@require_admin
@csrf_protect
async def update_password():
    """Update admin password"""
    data = await request.form
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not current_password or not new_password or not confirm_password:
        return jsonify({
            'success': False,
            'message': 'All password fields are required'
        }), 400
    
    # Validate password length
    if len(new_password) < 8:
        return jsonify({
            'success': False,
            'message': 'New password must be at least 8 characters long'
        }), 400
    
    # Check if new password matches confirmation
    if new_password != confirm_password:
        return jsonify({
            'success': False,
            'message': 'New passwords do not match'
        }), 400
    
    async with AsyncSessionLocal() as db_session:
        try:
            # Get current admin user
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == session['publisher_id'])
            )
            admin_user = result.scalar_one_or_none()
            
            if not admin_user:
                return jsonify({
                    'success': False,
                    'message': 'User not found'
                }), 404
            
            # Verify current password
            if not bcrypt.checkpw(current_password.encode('utf-8'), admin_user.password_hash.encode('utf-8')):
                logger.warning(f"Failed password change attempt for admin {admin_user.email} - incorrect password")
                return jsonify({
                    'success': False,
                    'message': 'Current password is incorrect'
                }), 401
            
            # Update password
            admin_user.password_hash = hash_password(new_password)
            await db_session.commit()
            
            logger.info(f"Admin password changed for {admin_user.email}")
            
            return jsonify({
                'success': True,
                'message': 'Password updated successfully'
            }), 200
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error updating admin password: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'An error occurred while updating password'
            }), 500
