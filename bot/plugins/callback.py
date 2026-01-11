from telethon.events import CallbackQuery
from bot import TelegramBot
from bot.modules.decorators import verify_user
from bot.modules.static import *
from bot.modules.telegram import get_message
from bot.database import AsyncSessionLocal
from bot.models import File
from sqlalchemy import select
import logging

logger = logging.getLogger('bot.plugins')

async def delete_file_from_db(message_id: int):
    """Delete file record from database"""
    from sqlalchemy import delete
    async with AsyncSessionLocal() as session:
        try:
            # Use delete statement instead of session.delete
            stmt = delete(File).where(File.telegram_message_id == message_id)
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount > 0:
                logger.info(f"Deleted file record for message {message_id}")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error deleting file from database: {e}")

@TelegramBot.on(CallbackQuery(pattern=r'^rm_'))
@verify_user(private=True)
async def delete_file(event: CallbackQuery.Event):
    query_data = event.query.data.decode().split('_')

    if len(query_data) != 3:
        return await event.answer(InvalidQueryText, alert=True)
    
    try:
        message_id = int(query_data[1])
    except ValueError:
        return await event.answer(InvalidQueryText, alert=True)

    message = await get_message(message_id)

    if not message:
        return await event.answer(MessageNotExist, alert=True)
    if query_data[2] != message.raw_text:
        return await event.answer(InvalidQueryText, alert=True)

    await message.delete()
    
    # Also delete from database
    await delete_file_from_db(message_id)

    return await event.answer(LinkRevokedText, alert=True)