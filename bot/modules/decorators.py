from telethon.events import NewMessage, CallbackQuery
from typing import Callable
from functools import wraps
from bot.config import Telegram
from bot.database import AsyncSessionLocal
from bot.models import Publisher
from sqlalchemy import select

def verify_user(private: bool = False):
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update: NewMessage.Event | CallbackQuery.Event):
            if private and not update.is_private:
                return

            chat_id = str(update.chat_id)

            if not Telegram.ALLOWED_USER_IDS or chat_id in Telegram.ALLOWED_USER_IDS:
                return await func(update)

        return wrapper
    return decorator

def verify_admin(private: bool = True):
    
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update: NewMessage.Event | CallbackQuery.Event):
            if private and not update.is_private:
                return
            
            if not update.sender:
                return
            
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Publisher).where(
                        Publisher.telegram_id == update.sender.id,
                        Publisher.is_admin == True
                    )
                )
                publisher = result.scalar_one_or_none()
                
                if not publisher:
                    await update.reply(
                        "❌ **Access Denied**\n\n"
                        "This command is only available to administrators."
                    )
                    return
                
                return await func(update)
        
        return wrapper
    return decorator