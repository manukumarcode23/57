import secrets
import string
from bot.database import AsyncSessionLocal
from bot.models import ReferralCode, Referral, ReferralSettings, ReferralReward, Publisher
from sqlalchemy import select
from datetime import datetime, timezone

async def generate_unique_referral_code() -> str:
    """Generate a unique referral code"""
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(ReferralCode).where(ReferralCode.referral_code == code)
            )
            existing = result.scalar_one_or_none()
            
            if not existing:
                return code

async def create_referral_code_for_publisher(publisher_id: int) -> str:
    """Create a referral code for a publisher"""
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(ReferralCode).where(ReferralCode.publisher_id == publisher_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            return existing.referral_code
        
        code = await generate_unique_referral_code()
        
        referral_code_obj = ReferralCode(
            publisher_id=publisher_id,
            referral_code=code,
            total_referrals=0,
            total_earnings=0.0
        )
        
        db_session.add(referral_code_obj)
        await db_session.commit()
        
        return code

async def validate_referral_code(code: str) -> tuple[bool, int | None]:
    """Validate a referral code and return (is_valid, referrer_id)"""
    if not code or len(code) != 8:
        return False, None
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(ReferralCode).where(ReferralCode.referral_code == code.upper())
        )
        referral_code_obj = result.scalar_one_or_none()
        
        if not referral_code_obj:
            return False, None
        
        publisher_result = await db_session.execute(
            select(Publisher).where(Publisher.id == referral_code_obj.publisher_id)
        )
        publisher = publisher_result.scalar_one_or_none()
        
        if not publisher or not publisher.is_active:
            return False, None
        
        return True, referral_code_obj.publisher_id

async def create_referral_relationship(referrer_id: int, referred_publisher_id: int, referral_code: str) -> bool:
    """Create a referral relationship and optionally credit registration reward"""
    import logging
    logger = logging.getLogger('bot')
    try:
        async with AsyncSessionLocal() as db_session:
            settings_result = await db_session.execute(select(ReferralSettings))
            settings = settings_result.scalar_one_or_none()
            
            if not settings or not settings.is_enabled:
                logger.warning(f"Referral system disabled or no settings found")
                return False
            
            existing_result = await db_session.execute(
                select(Referral).where(Referral.referred_publisher_id == referred_publisher_id)
            )
            existing = existing_result.scalar_one_or_none()
            
            if existing:
                logger.warning(f"Referral already exists for publisher {referred_publisher_id}")
                return False
            
            referral = Referral(
                referrer_id=referrer_id,
                referred_publisher_id=referred_publisher_id,
                referral_code=referral_code.upper(),
                status='active',
                total_rewards_earned=0.0,
                completed_withdrawals=0
            )
            
            db_session.add(referral)
            await db_session.commit()
            await db_session.refresh(referral)
            
            referral_code_result = await db_session.execute(
                select(ReferralCode).where(ReferralCode.publisher_id == referrer_id)
            )
            referral_code_obj = referral_code_result.scalar_one_or_none()
            
            if referral_code_obj:
                old_count = referral_code_obj.total_referrals
                referral_code_obj.total_referrals += 1
                await db_session.commit()
                logger.info(f"Updated referral count for publisher {referrer_id}: {old_count} -> {referral_code_obj.total_referrals}")
            else:
                logger.error(f"Referral code not found for referrer {referrer_id}")
            
            if settings.reward_on_registration and settings.registration_reward_amount > 0:
                await credit_referral_reward(
                    db_session=db_session,
                    referral_id=referral.id,
                    referrer_id=referrer_id,
                    referred_publisher_id=referred_publisher_id,
                    milestone_type='registration',
                    reward_amount=settings.registration_reward_amount
                )
            
            if settings.new_publisher_welcome_bonus_enabled and settings.new_publisher_welcome_bonus_amount > 0:
                new_publisher_result = await db_session.execute(
                    select(Publisher).where(Publisher.id == referred_publisher_id)
                )
                new_publisher = new_publisher_result.scalar_one_or_none()
                
                if new_publisher:
                    new_publisher.balance += settings.new_publisher_welcome_bonus_amount
                    await db_session.commit()
                    logger.info(f"Credited welcome bonus of ${settings.new_publisher_welcome_bonus_amount} to new publisher {referred_publisher_id}")
            
            return True
    except Exception as e:
        logger.error(f"Failed to create referral relationship: {str(e)}", exc_info=True)
        return False

async def credit_referral_reward(db_session, referral_id: int, referrer_id: int, referred_publisher_id: int, milestone_type: str, reward_amount: float, withdrawal_id: int | None = None):
    """Credit a referral reward to the referrer"""
    reward = ReferralReward(
        referral_id=referral_id,
        referrer_id=referrer_id,
        referred_publisher_id=referred_publisher_id,
        milestone_type=milestone_type,
        reward_amount=reward_amount,
        status='credited',
        credited_at=datetime.now(timezone.utc),
        withdrawal_id=withdrawal_id
    )
    
    db_session.add(reward)
    
    referrer_result = await db_session.execute(
        select(Publisher).where(Publisher.id == referrer_id)
    )
    referrer = referrer_result.scalar_one_or_none()
    
    if referrer:
        referrer.balance += reward_amount
    
    referral_result = await db_session.execute(
        select(Referral).where(Referral.id == referral_id)
    )
    referral = referral_result.scalar_one_or_none()
    
    if referral:
        referral.total_rewards_earned += reward_amount
    
    referral_code_result = await db_session.execute(
        select(ReferralCode).where(ReferralCode.publisher_id == referrer_id)
    )
    referral_code_obj = referral_code_result.scalar_one_or_none()
    
    if referral_code_obj:
        referral_code_obj.total_earnings += reward_amount
    
    await db_session.commit()

async def process_withdrawal_milestone(publisher_id: int, withdrawal_id: int):
    """Process referral rewards when a publisher completes a withdrawal"""
    try:
        async with AsyncSessionLocal() as db_session:
            settings_result = await db_session.execute(select(ReferralSettings))
            settings = settings_result.scalar_one_or_none()
            
            if not settings or not settings.is_enabled:
                return
            
            referral_result = await db_session.execute(
                select(Referral).where(Referral.referred_publisher_id == publisher_id)
            )
            referral = referral_result.scalar_one_or_none()
            
            if not referral:
                return
            
            referral.completed_withdrawals += 1
            await db_session.commit()
            
            withdrawal_count = referral.completed_withdrawals
            milestone_config = {
                1: ('first_withdrawal', settings.reward_on_first_withdrawal, settings.first_withdrawal_reward_amount),
                2: ('second_withdrawal', settings.reward_on_second_withdrawal, settings.second_withdrawal_reward_amount),
                3: ('third_withdrawal', settings.reward_on_third_withdrawal, settings.third_withdrawal_reward_amount),
                4: ('fourth_withdrawal', settings.reward_on_fourth_withdrawal, settings.fourth_withdrawal_reward_amount),
                5: ('fifth_withdrawal', settings.reward_on_fifth_withdrawal, settings.fifth_withdrawal_reward_amount),
            }
            
            if withdrawal_count in milestone_config:
                milestone_type, is_enabled, reward_amount = milestone_config[withdrawal_count]
                
                if is_enabled and reward_amount > 0:
                    existing_reward = await db_session.execute(
                        select(ReferralReward).where(
                            ReferralReward.referral_id == referral.id,
                            ReferralReward.milestone_type == milestone_type
                        )
                    )
                    if not existing_reward.scalar_one_or_none():
                        await credit_referral_reward(
                            db_session=db_session,
                            referral_id=referral.id,
                            referrer_id=referral.referrer_id,
                            referred_publisher_id=publisher_id,
                            milestone_type=milestone_type,
                            reward_amount=reward_amount,
                            withdrawal_id=withdrawal_id
                        )
    except Exception as e:
        pass
