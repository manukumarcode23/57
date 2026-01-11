from telethon import Button
from telethon.events import NewMessage
from telethon.tl.custom.message import Message
from bot import TelegramBot
from bot.config import Telegram
from bot.modules.static import *
from bot.modules.decorators import verify_user
from bot.modules.user_utils import save_user_to_db
from bot.database import AsyncSessionLocal
from bot.models import User, Publisher
from sqlalchemy import select
import logging

logger = logging.getLogger('bot.plugins')

async def check_linked_account_status(user_id: int):
    """Check if user's linked publisher account has valid API key"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Publisher).where(Publisher.telegram_id == user_id)
        )
        publisher = result.scalar_one_or_none()
        
        if not publisher:
            return None  # No account linked
        
        # Check if account has issues
        issues = []
        if not publisher.api_key:
            issues.append("❌ **API Key Missing**: Your linked publisher account no longer has an API key.")
        if not publisher.is_active:
            issues.append("❌ **Account Inactive**: Your publisher account has been deactivated.")
        
        if issues:
            return {
                'has_issues': True,
                'email': publisher.email,
                'issues': issues
            }
        
        return {
            'has_issues': False,
            'email': publisher.email
        }

@TelegramBot.on(NewMessage(incoming=True, pattern=r'^/start$'))
@verify_user(private=True)
async def welcome(event: NewMessage.Event | Message):
    if not event.sender:
        return
    
    # Save user to database
    await save_user_to_db(
        user_id=event.sender.id,
        username=getattr(event.sender, 'username', None),
        first_name=getattr(event.sender, 'first_name', None),
        last_name=getattr(event.sender, 'last_name', None)
    )
    
    # Check linked account status
    account_status = await check_linked_account_status(event.sender.id)
    
    welcome_message = WelcomeText % {'first_name': event.sender.first_name or 'User'}
    
    if account_status:
        if account_status['has_issues']:
            # Account has issues
            issues_text = "\n".join(account_status['issues'])
            warning_message = (
                f"\n\n⚠️ **Account Status Warning**\n\n"
                f"Linked Account: {account_status['email']}\n\n"
                f"{issues_text}\n\n"
                f"💡 **Solution**: Use /unlink to disconnect this account, "
                f"then /setapikey with a valid API key to link again."
            )
            welcome_message += warning_message
        else:
            # Account is valid
            welcome_message += (
                f"\n\n✅ **Linked Account**: {account_status['email']}\n"
                f"Your publisher account is active and ready to use!"
            )
    
    await event.reply(message=welcome_message)

@TelegramBot.on(NewMessage(incoming=True, pattern=r'^/setapikey'))
@verify_user(private=True)
async def set_api_key(event: NewMessage.Event | Message):
    if not event.sender or not event.message:
        logger.warning("setapikey command called without sender or message")
        return
    
    try:
        # Safely get message text using getattr
        message_text = getattr(event.message, 'text', None) or getattr(event.message, 'message', None)
        if not message_text:
            logger.warning(f"setapikey command called without message text by user {event.sender.id}")
            return
        
        command_parts = message_text.split(maxsplit=1)
        
        if len(command_parts) < 2:
            await event.reply(
                "**How to link your API key:**\n\n"
                "Usage: `/setapikey YOUR_API_KEY`\n\n"
                "Example: `/setapikey abc123def456...`\n\n"
                "Get your API key from the publisher dashboard."
            )
            return
        
        api_key = command_parts[1].strip()
        
        # Enhanced validation
        if not api_key or len(api_key) < 10:
            await event.reply("❌ Invalid API key format. API key must be at least 10 characters long.")
            logger.warning(f"Invalid API key format provided by user {event.sender.id}")
            return
        
        if len(api_key) > 128:
            await event.reply("❌ Invalid API key format. API key is too long.")
            logger.warning(f"Oversized API key provided by user {event.sender.id}")
            return
        
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(Publisher).where(Publisher.api_key == api_key).with_for_update()
                )
                publisher = result.scalar_one_or_none()
                
                if not publisher:
                    await event.reply(
                        "❌ **Invalid API Key**\n\n"
                        "This API key doesn't exist. Please:\n"
                        "1. Login to the publisher dashboard\n"
                        "2. Generate or copy your API key\n"
                        "3. Try again with the correct key"
                    )
                    logger.info(f"Non-existent API key attempt by user {event.sender.id}")
                    return
                
                if not publisher.is_active:
                    await event.reply("❌ Your publisher account is inactive. Please contact support.")
                    logger.warning(f"Inactive account link attempt: publisher_id={publisher.id}, user_id={event.sender.id}")
                    return
                
                if event.sender and publisher.telegram_id and publisher.telegram_id != event.sender.id:
                    await event.reply(
                        "❌ This API key is already linked to another Telegram account."
                    )
                    logger.warning(f"API key already linked: publisher_id={publisher.id}, existing_user={publisher.telegram_id}, attempted_by={event.sender.id}")
                    return
                
                if event.sender:
                    existing_result = await session.execute(
                        select(Publisher).where(
                            Publisher.telegram_id == event.sender.id,
                            Publisher.id != publisher.id
                        )
                    )
                    existing_publisher = existing_result.scalar_one_or_none()
                    
                    if existing_publisher:
                        await event.reply(
                            f"❌ **Already Linked**\n\n"
                            f"Your Telegram account is already linked to: {existing_publisher.email}\n\n"
                            f"To link a different account:\n"
                            f"1. Use /unlinkaccount to unlink the current one\n"
                            f"2. Then use /setapikey with the new API key"
                        )
                        logger.warning(f"User {event.sender.id} tried to link multiple accounts. Already linked to publisher {existing_publisher.id}")
                        return
                    
                    publisher.telegram_id = event.sender.id
                await session.commit()
                
                await event.reply(
                    "✅ **API Key Linked Successfully!**\n\n"
                    f"Your publisher account ({publisher.email}) is now connected to this Telegram account.\n\n"
                    "You can now upload files directly through this bot!"
                )
                logger.info(f"API key linked successfully: publisher_id={publisher.id}, user_id={event.sender.id}")
                
            except Exception as db_error:
                await session.rollback()
                logger.error(f"Database error in set_api_key for user {event.sender.id}: {db_error}", exc_info=True)
                await event.reply("❌ A database error occurred. Please try again in a moment.")
            
    except Exception as e:
        logger.error(f"Unexpected error in set_api_key for user {event.sender.id if event.sender else 'unknown'}: {e}", exc_info=True)
        await event.reply("❌ An unexpected error occurred. Please try again later.")

@TelegramBot.on(NewMessage(incoming=True, pattern=r'^/myaccount$'))
@verify_user(private=True)
async def my_account(event: NewMessage.Event | Message):
    if not event.sender:
        return
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Publisher).where(Publisher.telegram_id == event.sender.id)
        )
        publisher = result.scalar_one_or_none()
        
        if not publisher:
            await event.reply(
                "**No Publisher Account Linked**\n\n"
                "Use /setapikey to link your publisher account."
            )
            return
        
        api_key_status = "✅ Active" if publisher.api_key else "❌ Not Generated"
        account_status = "✅ Active" if publisher.is_active else "❌ Inactive"
        
        message = (
            f"**Your Publisher Account**\n\n"
            f"📧 Email: {publisher.email}\n"
            f"🔑 API Key: {api_key_status}\n"
            f"📊 Status: {account_status}\n"
            f"📅 Joined: {publisher.created_at.strftime('%Y-%m-%d')}"
        )
        
        # Add warning if there are issues
        if not publisher.api_key or not publisher.is_active:
            message += (
                f"\n\n⚠️ **Warning**: Your account has issues.\n"
                f"Use /unlink to disconnect, then /setapikey to reconnect with a valid API key."
            )
        else:
            message += f"\n\n💡 To link a different account, use /unlink first."
        
        await event.reply(message)

@TelegramBot.on(NewMessage(incoming=True, pattern=r'^/unlink$'))
@verify_user(private=True)
async def unlink_account(event: NewMessage.Event | Message):
    if not event.sender:
        return
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Publisher).where(Publisher.telegram_id == event.sender.id)
        )
        publisher = result.scalar_one_or_none()
        
        if not publisher:
            await event.reply(
                "**No Account Linked**\n\n"
                "You don't have any publisher account linked to this Telegram account."
            )
            return
        
        publisher_email = publisher.email
        publisher.telegram_id = None
        await session.commit()
        
        await event.reply(
            f"✅ **Account Unlinked Successfully!**\n\n"
            f"Your Telegram account has been disconnected from {publisher_email}.\n\n"
            f"You can now use /setapikey to link to a different publisher account."
        )