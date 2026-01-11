from quart import Blueprint, request, render_template, redirect, session
from bot.database import AsyncSessionLocal
from bot.models import ReferralSettings, ReferralCode, Referral, ReferralReward, Publisher
from sqlalchemy import select, func
from .utils import require_admin
from bot.server.security import get_csrf_token, csrf_protect

bp = Blueprint('admin_referrals', __name__)

@bp.route('/referral-settings')
@require_admin
async def referral_settings():
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(select(ReferralSettings))
        settings = result.scalar_one_or_none()
        
        if not settings:
            settings = ReferralSettings(
                is_enabled=True,
                reward_on_registration=False,
                registration_reward_amount=0.0,
                reward_on_first_withdrawal=True,
                first_withdrawal_reward_amount=2.0,
                reward_on_second_withdrawal=True,
                second_withdrawal_reward_amount=1.0,
                reward_on_third_withdrawal=False,
                third_withdrawal_reward_amount=0.0,
                reward_on_fourth_withdrawal=False,
                fourth_withdrawal_reward_amount=0.0,
                reward_on_fifth_withdrawal=False,
                fifth_withdrawal_reward_amount=0.0
            )
            db_session.add(settings)
            await db_session.commit()
        
        total_referrals = await db_session.scalar(select(func.count(Referral.id)))
        total_rewards = await db_session.scalar(select(func.sum(ReferralReward.reward_amount)).where(ReferralReward.status == 'credited'))
        active_referrers = await db_session.scalar(
            select(func.count(func.distinct(Referral.referrer_id))).where(Referral.status == 'active')
        )
        
        csrf_token = get_csrf_token()
        return await render_template(
            'admin_referral_settings.html', 
            active_page='referrals',
            settings=settings,
            total_referrals=total_referrals or 0,
            total_rewards=total_rewards or 0.0,
            active_referrers=active_referrers or 0,
            csrf_token=csrf_token
        )

@bp.route('/referral-settings/update', methods=['POST'])
@require_admin
@csrf_protect
async def update_referral_settings():
    data = await request.form
    
    async with AsyncSessionLocal() as db_session:
        try:
            result = await db_session.execute(select(ReferralSettings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = ReferralSettings()
                db_session.add(settings)
            
            settings.is_enabled = data.get('is_enabled') == 'on'
            
            settings.reward_on_registration = data.get('reward_on_registration') == 'on'
            registration_amount = data.get('registration_reward_amount', '0').strip()
            settings.registration_reward_amount = float(registration_amount) if registration_amount else 0.0
            
            settings.new_publisher_welcome_bonus_enabled = data.get('new_publisher_welcome_bonus_enabled') == 'on'
            welcome_bonus_amount = data.get('new_publisher_welcome_bonus_amount', '0').strip()
            settings.new_publisher_welcome_bonus_amount = float(welcome_bonus_amount) if welcome_bonus_amount else 0.0
            
            settings.reward_on_first_withdrawal = data.get('reward_on_first_withdrawal') == 'on'
            first_amount = data.get('first_withdrawal_reward_amount', '0').strip()
            settings.first_withdrawal_reward_amount = float(first_amount) if first_amount else 0.0
            
            settings.reward_on_second_withdrawal = data.get('reward_on_second_withdrawal') == 'on'
            second_amount = data.get('second_withdrawal_reward_amount', '0').strip()
            settings.second_withdrawal_reward_amount = float(second_amount) if second_amount else 0.0
            
            settings.reward_on_third_withdrawal = data.get('reward_on_third_withdrawal') == 'on'
            third_amount = data.get('third_withdrawal_reward_amount', '0').strip()
            settings.third_withdrawal_reward_amount = float(third_amount) if third_amount else 0.0
            
            settings.reward_on_fourth_withdrawal = data.get('reward_on_fourth_withdrawal') == 'on'
            fourth_amount = data.get('fourth_withdrawal_reward_amount', '0').strip()
            settings.fourth_withdrawal_reward_amount = float(fourth_amount) if fourth_amount else 0.0
            
            settings.reward_on_fifth_withdrawal = data.get('reward_on_fifth_withdrawal') == 'on'
            fifth_amount = data.get('fifth_withdrawal_reward_amount', '0').strip()
            settings.fifth_withdrawal_reward_amount = float(fifth_amount) if fifth_amount else 0.0
            
            await db_session.commit()
            
            return redirect('/admin/referral-settings?success=1')
            
        except (ValueError, TypeError) as e:
            await db_session.rollback()
            return redirect('/admin/referral-settings?error=invalid_format')
        except Exception as e:
            await db_session.rollback()
            return redirect('/admin/referral-settings?error=update_failed')

@bp.route('/referrals')
@require_admin
async def referrals():
    page = int(request.args.get('page', 1))
    per_page = 25
    
    async with AsyncSessionLocal() as db_session:
        total_referrals = await db_session.scalar(select(func.count(Referral.id)))
        
        result = await db_session.execute(
            select(Referral)
            .order_by(Referral.created_at.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
        referrals = result.scalars().all()
        
        referral_data = []
        for ref in referrals:
            referrer_result = await db_session.execute(
                select(Publisher).where(Publisher.id == ref.referrer_id)
            )
            referrer = referrer_result.scalar_one_or_none()
            
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
                'referrer': referrer,
                'referred': referred,
                'rewards': rewards
            })
        
        total_pages = (total_referrals + per_page - 1) // per_page if total_referrals else 1
        
        csrf_token = get_csrf_token()
        return await render_template(
            'admin_referrals.html',
            active_page='referrals',
            referral_data=referral_data,
            page=page,
            total_pages=total_pages,
            total_referrals=total_referrals or 0,
            csrf_token=csrf_token
        )
