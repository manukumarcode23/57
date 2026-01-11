import logging
import hashlib
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from sqlalchemy import select, func, and_, extract, text
from sqlalchemy.exc import IntegrityError
from bot.database import AsyncSessionLocal
from bot.models import PremiumLinkEarning, SubscriptionPlan, Publisher, File, Subscription

logger = logging.getLogger(__name__)

def get_monthly_limit_lock_id(android_id: str, plan_id: int) -> tuple[int, int]:
    """
    Generate a unique lock ID pair for monthly limit enforcement per (android_id, plan_id).
    Uses hashlib to create a stable 64-bit key from the combination.
    Returns (key1, key2) for use with pg_advisory_xact_lock(key1, key2).
    """
    combined = f"{android_id}:{plan_id}"
    hash_bytes = hashlib.sha256(combined.encode()).digest()
    key1 = int.from_bytes(hash_bytes[:4], byteorder='big', signed=False)
    key2 = int.from_bytes(hash_bytes[4:8], byteorder='big', signed=False)
    return (key1, key2)

async def process_premium_link_earning(
    subscription_id: int,
    publisher_id: int,
    android_id: str,
    hash_id: str,
    plan_id: int
) -> None:
    """
    Process earning for publisher when premium user generates links.
    
    This function runs in a separate transaction after link generation,
    so earning failures don't affect link delivery.
    
    Rules:
    - Only earn if file has publisher_id
    - Only earn if plan has earning_per_link > 0 and monthly_link_limit > 0
    - Daily uniqueness: same publisher+android_id+hash_id only earns once per day
    - Monthly limit: android_id can only generate limited earnings per month per plan
    
    Args:
        subscription_id: ID of the subscription
        publisher_id: ID of the publisher who owns the video
        android_id: Android device ID of the premium user
        hash_id: Hash ID of the video file
        plan_id: ID of the subscription plan
    """
    try:
        if not publisher_id:
            logger.debug(f"File {hash_id} has no publisher, skipping earning")
            return
        
        if not plan_id:
            logger.debug(f"Subscription {subscription_id} has no plan_id, skipping earning")
            return
        
        async with AsyncSessionLocal() as earning_session:
            async with earning_session.begin():
                plan_result = await earning_session.execute(
                    select(SubscriptionPlan).where(
                        SubscriptionPlan.id == plan_id,
                        SubscriptionPlan.is_active == True
                    )
                )
                plan = plan_result.scalar_one_or_none()
                
                if not plan:
                    logger.warning(f"Plan {plan_id} not found or inactive")
                    return
                
                if not plan.earning_per_link or plan.earning_per_link <= 0:
                    logger.debug(f"Plan {plan.name} has no earning_per_link, skipping")
                    return
                
                if not plan.monthly_link_limit or plan.monthly_link_limit <= 0:
                    logger.debug(f"Plan {plan.name} has no monthly_link_limit, skipping")
                    return
                
                key1, key2 = get_monthly_limit_lock_id(android_id, plan.id)
                await earning_session.execute(text(f"SELECT pg_advisory_xact_lock({key1}, {key2})"))
                logger.debug(f"Acquired advisory lock ({key1}, {key2}) for android_id {android_id}, plan_id {plan.id}")
                
                now = datetime.now(timezone.utc)
                current_date = now.date()
                
                first_day_of_month = current_date.replace(day=1)
                if current_date.month == 12:
                    first_day_of_next_month = current_date.replace(year=current_date.year + 1, month=1, day=1)
                else:
                    first_day_of_next_month = current_date.replace(month=current_date.month + 1, day=1)
                
                month_count_result = await earning_session.execute(
                    select(func.count(PremiumLinkEarning.id)).where(
                        and_(
                            PremiumLinkEarning.android_id == android_id,
                            PremiumLinkEarning.plan_id == plan.id,
                            PremiumLinkEarning.earning_date >= first_day_of_month,
                            PremiumLinkEarning.earning_date < first_day_of_next_month
                        )
                    )
                )
                month_count = month_count_result.scalar() or 0
                
                if month_count >= plan.monthly_link_limit:
                    logger.info(
                        f"Monthly limit reached for android_id {android_id}, "
                        f"plan {plan.name}: {month_count}/{plan.monthly_link_limit}"
                    )
                    return
                
                publisher_result = await earning_session.execute(
                    select(Publisher)
                    .where(Publisher.id == publisher_id)
                    .with_for_update()
                )
                publisher = publisher_result.scalar_one_or_none()
                
                if not publisher:
                    logger.warning(f"Publisher {publisher_id} not found")
                    return
                
                if not publisher.is_active:
                    logger.info(f"Publisher {publisher.id} is inactive, skipping earning")
                    return
                
                earning = PremiumLinkEarning(
                    publisher_id=publisher.id,
                    android_id=android_id,
                    hash_id=hash_id,
                    plan_id=plan.id,
                    subscription_id=subscription_id,
                    earning_amount=plan.earning_per_link,
                    earning_date=current_date
                )
                
                try:
                    earning_session.add(earning)
                    
                    publisher.balance += plan.earning_per_link
                    
                    await earning_session.flush()
                    
                    logger.info(
                        f"Earning created: Publisher {publisher.id} earned {plan.earning_per_link} "
                        f"from android_id {android_id}, hash_id {hash_id}, plan {plan.name}. "
                        f"New balance: {publisher.balance}"
                    )
                    
                except IntegrityError as e:
                    if 'uq_earning_daily' in str(e):
                        logger.debug(
                            f"Daily earning already recorded for publisher {publisher.id}, "
                            f"android_id {android_id}, hash_id {hash_id} on {current_date}"
                        )
                    else:
                        logger.exception(f"Integrity error creating earning: {e}")
                    await earning_session.rollback()
                    return
                
    except Exception as e:
        logger.exception(f"Error processing premium link earning: {e}")
