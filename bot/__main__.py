from importlib import import_module
from pathlib import Path
from bot import TelegramBot, logger
from bot.config import Telegram
from bot.server import server
import asyncio
from datetime import datetime, timedelta, timezone
from bot.database import AsyncSessionLocal
from bot.models import AdPlayCount, DeviceLink
from sqlalchemy import delete

def load_plugins():
    count = 0
    for path in Path('bot/plugins').rglob('*.py'):
        import_module(f'bot.plugins.{path.stem}')
        count += 1
    logger.info(f'Loaded {count} {"plugins" if count > 1 else "plugin"}.')

async def cleanup_old_play_counts():
    """Background task to clean up old ad play count records every 24 hours"""
    while True:
        try:
            await asyncio.sleep(86400)
            
            cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=7)
            
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    delete(AdPlayCount).where(AdPlayCount.play_date < cutoff_date)
                )
                deleted_count = result.rowcount
                await session.commit()
                
                if deleted_count > 0:
                    logger.info(f'Cleaned up {deleted_count} old ad play count records older than 7 days')
        except Exception as e:
            logger.error(f'Error in cleanup task: {e}')

async def cleanup_expired_device_links():
    """Background task to clean up expired device links every hour"""
    while True:
        try:
            await asyncio.sleep(3600)
            
            current_time = datetime.now(timezone.utc)
            
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    delete(DeviceLink).where(DeviceLink.link_expiry_time < current_time)
                )
                deleted_count = result.rowcount
                await session.commit()
                
                if deleted_count > 0:
                    logger.info(f'Cleaned up {deleted_count} expired device links')
        except Exception as e:
            logger.error(f'Error in device link cleanup task: {e}')

async def cleanup_expired_pending_payments():
    """Background task to clean up expired pending payments every 30 minutes"""
    while True:
        try:
            await asyncio.sleep(1800)  # Run every 30 minutes
            
            # Delete pending payments older than 15 minutes
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=15)
            
            async with AsyncSessionLocal() as session:
                from bot.models import Subscription
                result = await session.execute(
                    delete(Subscription).where(
                        Subscription.status == 'pending',
                        Subscription.created_at < cutoff_time
                    )
                )
                deleted_count = result.rowcount
                await session.commit()
                
                if deleted_count > 0:
                    logger.info(f'Cleaned up {deleted_count} expired pending payments')
        except Exception as e:
            logger.error(f'Error in pending payment cleanup task: {e}')

if __name__ == '__main__':
    logger.info('initializing...')
    TelegramBot.loop.create_task(server.serve())
    TelegramBot.loop.create_task(cleanup_old_play_counts())
    TelegramBot.loop.create_task(cleanup_expired_device_links())
    TelegramBot.loop.create_task(cleanup_expired_pending_payments())
    # BOT_TOKEN is guaranteed to be a string (raises ValueError if not set in config.py)
    bot_token: str = Telegram.BOT_TOKEN  # type: ignore
    TelegramBot.start(bot_token=bot_token)
    logger.info('Telegram client is now started.')
    logger.info('Loading bot plugins...')
    load_plugins()
    logger.info('Bot is now ready!')
    TelegramBot.run_until_disconnected()