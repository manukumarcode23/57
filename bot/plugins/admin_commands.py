from telethon.events import NewMessage
from telethon.tl.custom.message import Message
from bot import TelegramBot
from bot.modules.decorators import verify_admin
from bot.database import AsyncSessionLocal
from bot.models import Settings
from sqlalchemy import select
import logging
import re

logger = logging.getLogger('bot.plugins')

@TelegramBot.on(NewMessage(incoming=True, pattern=r'^/setminwithdrawal'))
@verify_admin(private=True)
async def set_minimum_withdrawal(event: NewMessage.Event | Message):
    if not event.sender:
        return
    
    if not event.raw_text:
        return
    
    command_text = event.raw_text.strip()
    match = re.match(r'^/setminwithdrawal\s+(\d+(?:\.\d+)?)\s*$', command_text)
    
    if not match:
        await event.reply(
            "❌ **Invalid Command Format**\n\n"
            "**Usage**: `/setminwithdrawal <amount>`\n\n"
            "**Example**: `/setminwithdrawal 25.50`\n\n"
            "Sets the minimum withdrawal amount for all publishers."
        )
        return
    
    try:
        amount = float(match.group(1))
        
        if amount < 0:
            await event.reply(
                "❌ **Invalid Amount**\n\n"
                "The minimum withdrawal amount must be a positive number."
            )
            return
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                settings = Settings(
                    terms_of_service='',
                    privacy_policy='',
                    impression_rate=0.0,
                    impression_cutback_percentage=0.0,
                    minimum_withdrawal=amount,
                    callback_mode='POST',
                    web_max_file_size_mb=2048,
                    web_upload_rate_limit=10,
                    web_upload_rate_window=3600,
                    api_rate_limit=100,
                    api_rate_window=3600
                )
                session.add(settings)
            else:
                old_amount = settings.minimum_withdrawal
                settings.minimum_withdrawal = amount
            
            await session.commit()
            
            logger.info(f"Admin {event.sender.id} set minimum withdrawal amount to ${amount}")
            
            await event.reply(
                f"✅ **Minimum Withdrawal Amount Updated**\n\n"
                f"The minimum withdrawal amount has been set to **${amount:.2f}**\n\n"
                f"All publishers must now withdraw at least this amount."
            )
    
    except ValueError:
        await event.reply(
            "❌ **Invalid Amount**\n\n"
            "Please provide a valid number for the withdrawal amount."
        )
    except Exception as e:
        logger.error(f"Error setting minimum withdrawal amount: {e}")
        await event.reply(
            "❌ **Error**\n\n"
            "An error occurred while updating the minimum withdrawal amount. Please try again."
        )

@TelegramBot.on(NewMessage(incoming=True, pattern=r'^/getminwithdrawal$'))
@verify_admin(private=True)
async def get_minimum_withdrawal(event: NewMessage.Event | Message):
    if not event.sender:
        return
    
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Settings))
            settings = result.scalar_one_or_none()
            
            if not settings:
                minimum_withdrawal = 10.0
            else:
                minimum_withdrawal = settings.minimum_withdrawal
            
            await event.reply(
                f"ℹ️ **Current Minimum Withdrawal Amount**\n\n"
                f"The current minimum withdrawal amount is **${minimum_withdrawal:.2f}**"
            )
    
    except Exception as e:
        logger.error(f"Error getting minimum withdrawal amount: {e}")
        await event.reply(
            "❌ **Error**\n\n"
            "An error occurred while retrieving the minimum withdrawal amount."
        )
