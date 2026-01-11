from quart import Blueprint, request, render_template, redirect
from bot.database import AsyncSessionLocal
from bot.models import WithdrawalRequest, Publisher, BankAccount, Settings
from bot.server.security import csrf_protect, get_csrf_token
from sqlalchemy import select, func
from datetime import datetime, timezone
from .utils import require_admin
from bot.server.referral_helper import process_withdrawal_milestone

bp = Blueprint('admin_withdrawals', __name__)

@bp.route('/withdrawals')
@require_admin
async def withdrawals():
    status_filter = request.args.get('status', 'all')
    
    async with AsyncSessionLocal() as db_session:
        query = select(WithdrawalRequest).order_by(WithdrawalRequest.requested_at.desc())
        
        if status_filter != 'all':
            query = query.where(WithdrawalRequest.status == status_filter)
        
        result = await db_session.execute(query)
        withdrawal_requests = result.scalars().all()
        
        withdrawal_data = []
        for wr in withdrawal_requests:
            publisher_result = await db_session.execute(
                select(Publisher).where(Publisher.id == wr.publisher_id)
            )
            publisher = publisher_result.scalar_one_or_none()
            
            bank_result = await db_session.execute(
                select(BankAccount).where(BankAccount.id == wr.bank_account_id)
            )
            bank_account = bank_result.scalar_one_or_none()
            
            withdrawal_data.append({
                'withdrawal': wr,
                'publisher': publisher,
                'bank_account': bank_account
            })
        
        total_pending = await db_session.scalar(
            select(func.count(WithdrawalRequest.id)).where(WithdrawalRequest.status == 'pending')
        )
        total_approved = await db_session.scalar(
            select(func.count(WithdrawalRequest.id)).where(WithdrawalRequest.status == 'approved')
        )
        total_rejected = await db_session.scalar(
            select(func.count(WithdrawalRequest.id)).where(WithdrawalRequest.status == 'rejected')
        )
        
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        
        if not settings:
            settings = Settings(minimum_withdrawal=10.0, withdrawal_enabled=True)
            db_session.add(settings)
            await db_session.commit()
    
    csrf_token = get_csrf_token()
    return await render_template('admin_withdrawals.html',
                                  active_page='withdrawals',
                                  withdrawal_data=withdrawal_data,
                                  status_filter=status_filter,
                                  total_pending=total_pending or 0,
                                  total_approved=total_approved or 0,
                                  total_rejected=total_rejected or 0,
                                  minimum_withdrawal=settings.minimum_withdrawal if settings else 10.0,
                                  withdrawal_enabled=settings.withdrawal_enabled if settings else True,
                                  csrf_token=csrf_token)

@bp.route('/withdrawal/toggle-requests', methods=['POST'])
@require_admin
@csrf_protect
async def toggle_withdrawal_requests():
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = Settings(withdrawal_enabled=False)
                db_session.add(settings)
            else:
                settings.withdrawal_enabled = not settings.withdrawal_enabled
            
            await db_session.commit()
            status = "enabled" if settings.withdrawal_enabled else "disabled"
            return redirect(f'/admin/withdrawals?success=Withdrawal requests have been {status}')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/withdrawals?error=Failed to toggle withdrawal requests')

@bp.route('/withdrawal/approve/<int:withdrawal_id>', methods=['POST'])
@require_admin
@csrf_protect
async def approve_withdrawal(withdrawal_id):
    data = await request.form
    admin_note = data.get('admin_note', '').strip()
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(WithdrawalRequest).where(WithdrawalRequest.id == withdrawal_id)
            )
            withdrawal = result.scalar_one_or_none()
            
            if withdrawal and withdrawal.status == 'pending':
                publisher_result = await db_session.execute(
                    select(Publisher).where(Publisher.id == withdrawal.publisher_id)
                )
                publisher = publisher_result.scalar_one_or_none()
                
                if not publisher:
                    withdrawal.status = 'rejected'
                    withdrawal.admin_note = "Publisher not found"
                    withdrawal.processed_at = datetime.now(timezone.utc)
                    await db_session.commit()
                else:
                    withdrawal.status = 'approved'
                    withdrawal.admin_note = admin_note
                    withdrawal.processed_at = datetime.now(timezone.utc)
                    
                    await db_session.commit()
                    
                    await process_withdrawal_milestone(withdrawal.publisher_id, withdrawal_id)
            
            return redirect('/admin/withdrawals')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/withdrawals')

@bp.route('/withdrawal/reject/<int:withdrawal_id>', methods=['POST'])
@require_admin
@csrf_protect
async def reject_withdrawal(withdrawal_id):
    data = await request.form
    admin_note = data.get('admin_note', '').strip()
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(
                select(WithdrawalRequest).where(WithdrawalRequest.id == withdrawal_id)
            )
            withdrawal = result.scalar_one_or_none()
            
            if withdrawal and withdrawal.status == 'pending':
                publisher_result = await db_session.execute(
                    select(Publisher).where(Publisher.id == withdrawal.publisher_id)
                )
                publisher = publisher_result.scalar_one_or_none()
                
                if publisher:
                    publisher.balance += withdrawal.amount  # Re-credit the balance
                
                withdrawal.status = 'rejected'
                withdrawal.admin_note = admin_note
                withdrawal.processed_at = datetime.now(timezone.utc)
                
                await db_session.commit()
            
            return redirect('/admin/withdrawals')
            
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/withdrawals')

@bp.route('/withdrawal/update-minimum', methods=['POST'])
@require_admin
@csrf_protect
async def update_minimum_withdrawal():
    data = await request.form
    minimum_withdrawal_str = data.get('minimum_withdrawal', '10.0').strip()
    
    async with AsyncSessionLocal() as db_session:
        try:
            minimum_withdrawal = float(minimum_withdrawal_str) if minimum_withdrawal_str else 10.0
            
            if minimum_withdrawal < 0:
                return redirect('/admin/withdrawals?error=Minimum withdrawal must be positive')
            
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            
            if not settings:
                settings = Settings(minimum_withdrawal=minimum_withdrawal)
                db_session.add(settings)
            else:
                settings.minimum_withdrawal = minimum_withdrawal
            
            await db_session.commit()
            return redirect('/admin/withdrawals?success=Minimum withdrawal updated successfully')
            
        except (ValueError, TypeError):
            await db_session.rollback()
            return redirect('/admin/withdrawals?error=Invalid amount format')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/withdrawals?error=Failed to update minimum withdrawal')
