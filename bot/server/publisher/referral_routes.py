from quart import Blueprint, request, render_template, redirect, session
from bot.database import AsyncSessionLocal
from bot.models import ReferralCode, Referral, ReferralReward, ReferralSettings, Publisher
from bot.server.security import get_csrf_token
from sqlalchemy import select, func
from .utils import require_publisher
import logging

bp = Blueprint('publisher_referrals', __name__)
logger = logging.getLogger('bot.server')

@bp.route('/referrals')
@require_publisher
async def referrals():
    publisher_id = session.get('publisher_id')
    publisher_email = session.get('publisher_email', 'Unknown')
    
    if not publisher_id:
        logger.warning("Referral page accessed without valid publisher session")
        return redirect('/login?error=Session expired. Please login again.')
    
    async with AsyncSessionLocal() as db_session:
        try:
            settings_result = await db_session.execute(select(ReferralSettings))
            settings = settings_result.scalar_one_or_none()
            
            if not settings or not settings.is_enabled:
                csrf_token = get_csrf_token()
                return await render_template('publisher_referrals.html',
                                              active_page='referrals',
                                              email=publisher_email,
                                              system_disabled=True,
                                              referral_code=None,
                                              referral_data=[],
                                              settings=None,
                                              total_pending_rewards=0.0,
                                              csrf_token=csrf_token)
            
            referral_code_result = await db_session.execute(
                select(ReferralCode).where(ReferralCode.publisher_id == publisher_id)
            )
            referral_code_obj = referral_code_result.scalar_one_or_none()
            
            if not referral_code_obj:
                from bot.server.referral_helper import create_referral_code_for_publisher
                code = await create_referral_code_for_publisher(publisher_id)
                referral_code_result = await db_session.execute(
                    select(ReferralCode).where(ReferralCode.publisher_id == publisher_id)
                )
                referral_code_obj = referral_code_result.scalar_one_or_none()
            
            referrals_result = await db_session.execute(
                select(Referral).where(Referral.referrer_id == publisher_id).order_by(Referral.created_at.desc())
            )
            referrals = referrals_result.scalars().all()
            
            referral_data = []
            for ref in referrals:
                referred_result = await db_session.execute(
                    select(Publisher).where(Publisher.id == ref.referred_publisher_id)
                )
                referred = referred_result.scalar_one_or_none()
                
                rewards_result = await db_session.execute(
                    select(ReferralReward)
                    .where(ReferralReward.referral_id == ref.id)
                    .order_by(ReferralReward.created_at.desc())
                )
                rewards = rewards_result.scalars().all()
                
                referral_data.append({
                    'referral': ref,
                    'referred': referred,
                    'rewards': rewards
                })
            
            total_pending_rewards = await db_session.scalar(
                select(func.sum(ReferralReward.reward_amount))
                .where(
                    ReferralReward.referrer_id == publisher_id,
                    ReferralReward.status == 'pending'
                )
            )
            
            csrf_token = get_csrf_token()
            return await render_template(
                'publisher_referrals.html',
                active_page='referrals',
                email=publisher_email,
                referral_code=referral_code_obj,
                referral_data=referral_data,
                settings=settings,
                total_pending_rewards=total_pending_rewards or 0.0,
                csrf_token=csrf_token
            )
        except Exception as e:
            logger.error(f"Error loading referral page for publisher {publisher_id}: {str(e)}", exc_info=True)
            csrf_token = get_csrf_token()
            return await render_template('publisher_referrals.html',
                                          active_page='referrals',
                                          email=publisher_email,
                                          system_disabled=True,
                                          error_message='Unable to load referral information. Please try again later.',
                                          referral_code=None,
                                          referral_data=[],
                                          settings=None,
                                          total_pending_rewards=0.0,
                                          csrf_token=csrf_token)
