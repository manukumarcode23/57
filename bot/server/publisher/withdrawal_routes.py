from quart import Blueprint, request, render_template, redirect, session
from bot.database import AsyncSessionLocal
from bot.models import Publisher, BankAccount, WithdrawalRequest, Settings
from bot.server.publisher.utils import require_publisher
from bot.server.security import csrf_protect, get_csrf_token
from sqlalchemy import select, and_
import logging

bp = Blueprint('publisher_withdrawal', __name__)
logger = logging.getLogger('bot.server')

@bp.route('/withdraw')
@require_publisher
async def withdraw():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Publisher).where(Publisher.id == session['publisher_id'])
        )
        publisher = result.scalar_one_or_none()
        
        bank_result = await db_session.execute(
            select(BankAccount).where(
                and_(
                    BankAccount.publisher_id == session['publisher_id'],
                    BankAccount.is_active == True
                )
            ).order_by(BankAccount.created_at.desc())
        )
        bank_account = bank_result.scalar_one_or_none()
        
        withdrawals_result = await db_session.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.publisher_id == session['publisher_id']
            ).order_by(WithdrawalRequest.requested_at.desc())
        )
        withdrawals = withdrawals_result.scalars().all()
        
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        minimum_withdrawal = settings.minimum_withdrawal if settings else 10.0
    
    csrf_token = get_csrf_token()
    
    async with AsyncSessionLocal() as db_session:
        settings_result = await db_session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        withdrawal_enabled = settings.withdrawal_enabled if settings else True

    return await render_template('publisher_withdraw.html',
                                  active_page='withdraw',
                                  email=session['publisher_email'],
                                  balance=publisher.balance if publisher else 0.0,
                                  bank_account=bank_account,
                                  withdrawals=withdrawals,
                                  minimum_withdrawal=minimum_withdrawal,
                                  withdrawal_enabled=withdrawal_enabled,
                                  message=request.args.get('message'),
                                  csrf_token=csrf_token)

@bp.route('/save-bank-account', methods=['POST'])
@require_publisher
@csrf_protect
async def save_bank_account():
    data = await request.form
    
    async with AsyncSessionLocal() as db_session:
        try:
            existing_result = await db_session.execute(
                select(BankAccount).where(
                    and_(
                        BankAccount.publisher_id == session['publisher_id'],
                        BankAccount.is_active == True
                    )
                )
            )
            existing_account = existing_result.scalar_one_or_none()
            
            if existing_account:
                existing_account.account_holder_name = data.get('account_holder_name', '')
                existing_account.bank_name = data.get('bank_name', '')
                existing_account.account_number = data.get('account_number', '')
                existing_account.ifsc_code = data.get('ifsc_code', '').upper()
                existing_account.branch_name = data.get('branch_name', '')
                existing_account.trc20_address = data.get('trc20_address', '')
                existing_account.bep20_address = data.get('bep20_address', '')
                existing_account.country = 'India'
            else:
                bank_account = BankAccount(
                    publisher_id=session['publisher_id'],
                    account_holder_name=data.get('account_holder_name', ''),
                    bank_name=data.get('bank_name', ''),
                    account_number=data.get('account_number', ''),
                    ifsc_code=data.get('ifsc_code', '').upper(),
                    branch_name=data.get('branch_name', ''),
                    trc20_address=data.get('trc20_address', ''),
                    bep20_address=data.get('bep20_address', ''),
                    country='India'
                )
                db_session.add(bank_account)
            
            await db_session.commit()
            
            logger.info(f"Bank account saved for publisher {session['publisher_email']}")
            
            message = 'Bank account saved successfully'
            if data.get('trc20_address') or data.get('bep20_address'):
                message = 'Payment details saved successfully'
                
            return redirect(f'/publisher/withdraw?message={message}')
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error saving bank account: {e}")
            return redirect('/publisher/withdraw?message=Failed to save bank account')

@bp.route('/request-withdrawal', methods=['POST'])
@require_publisher
@csrf_protect
async def request_withdrawal():
    data = await request.form
    
    try:
        amount = float(data.get('amount', 0))
    except (ValueError, TypeError):
        return redirect('/publisher/withdraw?message=Invalid withdrawal amount')
    
    async with AsyncSessionLocal() as db_session:
        try:
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            if settings and not settings.withdrawal_enabled:
                return redirect('/publisher/withdraw?message=Withdrawals are temporarily disabled by admin')

            result = await db_session.execute(
                select(Publisher).where(Publisher.id == session['publisher_id']).with_for_update()
            )
            publisher = result.scalar_one_or_none()
            
            bank_result = await db_session.execute(
                select(BankAccount).where(
                    and_(
                        BankAccount.publisher_id == session['publisher_id'],
                        BankAccount.is_active == True
                    )
                )
            )
            bank_account = bank_result.scalar_one_or_none()
            
            if not bank_account:
                return redirect('/publisher/withdraw?message=Please add bank account first')
            
            settings_result = await db_session.execute(select(Settings))
            settings = settings_result.scalar_one_or_none()
            minimum_withdrawal = settings.minimum_withdrawal if settings else 10.0
            
            if not publisher:
                return redirect('/publisher/withdraw?message=Publisher not found')
            
            if amount < minimum_withdrawal:
                return redirect(f'/publisher/withdraw?message=Minimum withdrawal amount is ${minimum_withdrawal}')
            
            if amount > publisher.balance:
                return redirect('/publisher/withdraw?message=Insufficient balance')
            
            publisher.balance -= amount
            
            withdrawal = WithdrawalRequest(
                publisher_id=session['publisher_id'],
                bank_account_id=bank_account.id,
                amount=amount,
                status='pending'
            )
            db_session.add(withdrawal)
            
            await db_session.commit()
            
            logger.info(f"Withdrawal requested by publisher {session['publisher_email']}: ${amount}")
            
            return redirect('/publisher/withdraw?message=Withdrawal request submitted successfully')
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error requesting withdrawal: {e}")
            return redirect('/publisher/withdraw?message=Failed to submit withdrawal request')
