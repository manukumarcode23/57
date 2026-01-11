"""
User utility functions for common user operations
"""

import logging
from bot.database import AsyncSessionLocal
from bot.models import User
from sqlalchemy import select

logger = logging.getLogger('bot.utils')


async def save_user_to_db(user_id: int, username: str | None, first_name: str | None, last_name: str | None):
    """
    Save or update user information in database
    
    Args:
        user_id: Telegram user ID
        username: Telegram username (optional)
        first_name: User's first name (optional)
        last_name: User's last name (optional)
    """
    async with AsyncSessionLocal() as session:
        try:
            # Check if user already exists by telegram_id
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            existing_user = result.scalar_one_or_none()
            
            if not existing_user:
                user_record = User(
                    telegram_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    is_allowed=True
                )
                session.add(user_record)
            else:
                # Update existing user info
                if username is not None:
                    existing_user.username = username
                if first_name is not None:
                    existing_user.first_name = first_name
                if last_name is not None:
                    existing_user.last_name = last_name
            
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Error saving user to database: {e}", exc_info=True)
