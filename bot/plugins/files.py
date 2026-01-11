from telethon import Button
from telethon.events import NewMessage
from telethon.tl.custom import Message
from secrets import token_hex
from bot import TelegramBot
from bot.config import Telegram, Server
from bot.modules.decorators import verify_user
from bot.modules.telegram import send_file_with_caption, filter_files
from bot.modules.file_validator import validate_file_type
from bot.modules.user_utils import save_user_to_db
from bot.modules.static import *
from bot.database import AsyncSessionLocal
from bot.models import File, User, Publisher, RateLimit, Settings
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone
import asyncio
import logging
import os
from pathlib import Path

from bot.database import generate_unique_access_code
from bot.modules.r2_storage import upload_file_to_r2

logger = logging.getLogger('bot.plugins')

async def save_file_to_db(message_id: int, filename: str, file_size: int, mime_type: str, access_code: str, video_duration = None, publisher_id = None, thumbnail_file_id = None, r2_key = None):
    """Save file information to database"""
    async with AsyncSessionLocal() as session:
        try:
            file_record = File(
                telegram_message_id=message_id,
                filename=filename,
                file_size=file_size,
                mime_type=mime_type,
                access_code=access_code,
                video_duration=int(video_duration) if video_duration else None,
                thumbnail_file_id=thumbnail_file_id,
                publisher_id=publisher_id,
                r2_object_key=r2_key
            )
            session.add(file_record)
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Error saving file to database: {e}")

@TelegramBot.on(NewMessage(incoming=True, func=filter_files))
@verify_user(private=True)
async def user_file_handler(event: NewMessage.Event | Message):
    if not event.sender:
        return
    
    # Check if the message is a TeraBox link
    message_text = ""
    if hasattr(event, 'message') and event.message:
        if isinstance(event.message, str):
            message_text = event.message
        elif hasattr(event.message, 'text') and event.message.text:
            message_text = event.message.text
    elif hasattr(event, 'text') and event.text:
        message_text = event.text

    terabox_url = None
    
    # Get dynamic domains from settings
    async with AsyncSessionLocal() as session:
        settings_result = await session.execute(select(Settings))
        settings = settings_result.scalar_one_or_none()
        supported_domains = settings.terabox_domains.split(',') if settings and settings.terabox_domains else ['terabox.com', '1024tera.com', 'terasharefile.com']

    if any(domain.strip() in message_text.lower() for domain in supported_domains if domain.strip()):
        # Simple extraction - find the URL
        import re
        urls = re.findall(r'(https?://[^\s]+)', message_text)
        for url in urls:
            url_lower = url.lower()
            if any(domain.strip() in url_lower for domain in supported_domains if domain.strip()):
                terabox_url = url
                break
    
    publisher_id = None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Publisher).where(Publisher.telegram_id == event.sender.id)
        )
        publisher = result.scalar_one_or_none()
        
        if not publisher or not publisher.is_active:
            await event.reply(
                "❌ **Access Denied**\n\n"
                "Only publishers can upload files through this bot.\n\n"
                "If you are a publisher:\n"
                "1. Get your API key from the publisher dashboard\n"
                "2. Use the /setapikey command to link your account"
            )
            return
        
        if not publisher.api_key:
            await event.reply(
                "❌ **No API Key Found**\n\n"
                "Please generate an API key from the publisher dashboard first, "
                "then link it using /setapikey command."
            )
            return
        
        publisher_id = publisher.id
    
    await save_user_to_db(
        user_id=event.sender.id,
        username=getattr(event.sender, 'username', None),
        first_name=getattr(event.sender, 'first_name', None),
        last_name=getattr(event.sender, 'last_name', None)
    )
    
    if terabox_url:
        logger.info(f"Processing TeraBox link: {terabox_url} from publisher {publisher_id}")
        status_msg = await event.reply("⏳ **Processing TeraBox Link...**")
        
        secret_code = await generate_unique_access_code()
        
        async with AsyncSessionLocal() as session:
            try:
                file_record = File(
                    telegram_message_id=int(datetime.now(timezone.utc).timestamp()), # Placeholder ID
                    filename=f"TeraBox_Video_{secret_code[:8]}",
                    file_size=0,
                    mime_type="video/mp4",
                    access_code=secret_code,
                    publisher_id=publisher_id,
                    custom_description=terabox_url
                )
                session.add(file_record)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Error saving TeraBox file to database: {e}")
                if status_msg:
                    await status_msg.edit("❌ **Database error while processing link.**")
                return

        play_link = f'{Server.BASE_URL}/play/{secret_code}'
        
        if status_msg:
            await status_msg.delete()
        await event.reply(
            message=f'✅ **TeraBox link processed successfully!**\n\n'
                    f'**File Code:** `{secret_code}`\n\n'
                    f'**Link:** {terabox_url}\n\n'
                    f'_Use the buttons below to access your file_',
            buttons=[
                [
                    Button.url('📱 Open Link', play_link)
                ]
            ]
        )
        return

    # Get file properties for validation BEFORE sending to channel
    filename = 'Unknown'
    video_duration = None
    thumbnail_file_id = None
    
    if hasattr(event, 'file') and event.file and event.file.name:
        filename = event.file.name
    elif event.document and event.document.attributes:
        for attr in event.document.attributes:
            if hasattr(attr, 'file_name'):
                try:
                    filename = attr.file_name  # type: ignore
                    break
                except AttributeError:
                    pass
            if hasattr(attr, 'duration'):
                try:
                    video_duration = attr.duration  # type: ignore
                except AttributeError:
                    pass
        # Extract thumbnail for documents with video content
        if event.document and hasattr(event.document, 'thumbs') and event.document.thumbs:
            try:
                # Use document ID for thumbnail reference (PhotoSize doesn't have file_id)
                thumbnail_file_id = str(event.document.id) if hasattr(event.document, 'id') else None
            except (AttributeError, IndexError, Exception) as e:
                logger.debug(f"Could not extract thumbnail: {e}")
    elif event.video:
        filename = 'Video_File'
        if hasattr(event.video, 'attributes') and event.video.attributes:
            for attr in event.video.attributes:
                if hasattr(attr, 'duration'):
                    try:
                        video_duration = attr.duration  # type: ignore
                        break
                    except AttributeError:
                        pass
        # Extract thumbnail for video files
        if hasattr(event.video, 'thumbs') and event.video.thumbs:
            try:
                # Use video ID for thumbnail reference (PhotoSize doesn't have file_id)
                thumbnail_file_id = str(event.video.id) if hasattr(event.video, 'id') else None
            except (AttributeError, IndexError, Exception) as e:
                logger.debug(f"Could not extract thumbnail: {e}")
    
    file_size = 0
    mime_type = 'application/octet-stream'
    
    if hasattr(event, 'document') and event.document:
        file_size = getattr(event.document, 'size', 0)
        mime_type = getattr(event.document, 'mime_type', 'application/octet-stream')
    elif hasattr(event, 'video') and event.video:
        file_size = getattr(event.video, 'size', 0)
        mime_type = getattr(event.video, 'mime_type', 'video/mp4')

    if file_size <= 0:
        await event.reply(
            "❌ **Invalid File**\n\n"
            "The file appears to be empty or corrupted.\n"
            "Please try uploading a valid file."
        )
        logger.warning(f"Invalid file size {file_size} uploaded by user {event.sender.id}")
        return
    
    # Security validation removed - files are uploaded directly
    logger.info(f"Processing file upload for {filename} by publisher {publisher_id}")
    
    # Show "Uploading..." status
    status_msg = await event.reply("⏳ **Uploading...**\n\n_Please wait while I process your file._")
    
    secret_code = await generate_unique_access_code()
    
    # Handle R2 upload in the background
    async def background_tasks():
        temp_file_path = f'/tmp/upload_{secret_code}_{filename}'
        try:
            r2_key = None
            # Download file to temp for R2 upload
            logger.info(f"Downloading media to {temp_file_path} for background tasks...")
            await event.download_media(file=temp_file_path)
            
            # Start R2 upload task
            try:
                logger.info(f"Uploading {temp_file_path} to R2 in background...")
                r2_key = await upload_file_to_r2(temp_file_path, f"{secret_code}/{filename}")
            except Exception as e:
                logger.error(f"R2 upload error: {e}")

            # Update database with R2 key
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(File).where(File.access_code == secret_code))
                file_rec = result.scalar_one_or_none()
                if file_rec:
                    file_rec.r2_object_key = r2_key
                    await session.commit()
            
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                
        except Exception as e:
            logger.error(f"Error in background upload tasks: {e}")
            
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    # Send file to channel first to get message_id
    message = await send_file_with_caption(event.message, f'`{secret_code}`')  # type: ignore
    message_id = message.id

    # Save initial record to database
    await save_file_to_db(
        message_id=message_id,
        filename=filename,
        file_size=file_size,
        mime_type=mime_type,
        access_code=secret_code,
        video_duration=video_duration,
        thumbnail_file_id=None,
        publisher_id=publisher_id,
        r2_key=None
    )

    # Start background tasks
    asyncio.create_task(background_tasks())

    play_link = f'{Server.BASE_URL}/play/{secret_code}'
    
    # Delete the "Uploading..." status message
    try:
        if status_msg:
            await status_msg.delete()
    except:
        pass

    await event.reply(
        message=f'✅ **File uploaded successfully!**\n\n'
                f'**File Code:** `{secret_code}`\n\n'
                f'_Use the buttons below to access your file_',
        buttons=[
            [
                Button.url('📱 Open Link', play_link)
            ],
            [
                Button.inline('🗑 Revoke Access', f'rm_{message_id}_{secret_code}')
            ]
        ]
    )

