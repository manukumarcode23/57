from telethon.events import NewMessage
from telethon.tl.custom import Message
from datetime import datetime, timezone
from mimetypes import guess_type
from bot import TelegramBot
from bot.config import Telegram
from bot.server.error import abort

async def get_message(message_id: int) -> Message | None:
    """
    Retrieve a message from Telegram by its ID.
    Returns None if message not found or error occurs.
    """
    try:
        result = await TelegramBot.get_messages(Telegram.CHANNEL_ID, ids=message_id)
        # get_messages can return a single Message, list, or None
        if result is None:
            return None
        elif isinstance(result, list):
            return result[0] if result else None  # type: ignore
        else:
            return result  # type: ignore
    except Exception:
        return None

async def send_file_with_caption(message: Message, caption: str, send_to: int = Telegram.CHANNEL_ID) -> Message:
    result = await TelegramBot.send_file(entity=send_to, file=message, caption=caption)  # type: ignore
    return result  # type: ignore

def filter_files(event: NewMessage.Event | Message):
    """Filter for files, videos, and text messages that might contain links"""
    from bot.database import AsyncSessionLocal
    from bot.models import Settings
    from sqlalchemy import select
    import asyncio

    # Accept text messages that contain TeraBox-like links
    message_text = None
    if hasattr(event, 'message') and event.message:
        if hasattr(event.message, 'text') and event.message.text:
            message_text = event.message.text
        elif isinstance(event.message, str):
            message_text = event.message
    elif hasattr(event, 'text') and event.text:
        message_text = event.text

    if message_text:
        text = message_text.lower()
        if 'http' in text:
            # Get domains from database (sync-like check using a helper or hardcoded defaults as fallback)
            # For simplicity in filter, we check against a common list and then verify in handler
            # or we can use a global cache if performance is an issue.
            # Here we'll check the default ones + any mention of 'tera' or 'share' to be safe
            common_keywords = ['terabox', '1024tera', 'terasharefile', 'tera', 'share']
            if any(kw in text for kw in common_keywords):
                return True

    # Accept actual files
    has_media = bool(
        (
            event.document
            or event.photo
            or event.video
            or event.video_note
            or event.audio
            or event.gif
        )
        and not event.sticker
    )
    return has_media

def get_file_properties(message: Message):
    if not message.file:
        abort(400, 'No file attached to message.')
    
    assert message.file is not None  # Type guard for LSP
    file_name = message.file.name
    file_size = message.file.size or 0
    mime_type = message.file.mime_type

    if not file_name:
        attributes = {
            'video': 'mp4',
            'audio': 'mp3',
            'voice': 'ogg',
            'photo': 'jpg',
            'video_note': 'mp4'
        }

        media = None
        file_type = None
        file_format = None
        
        for attribute in attributes:
            media = getattr(message, attribute, None)
            if media:
                file_type, file_format = attribute, attributes[attribute]
                break
        
        if not media:
            abort(400, 'Invalid media type.')

        date = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f'{file_type}-{date}.{file_format}'
    
    if not mime_type:
        mime_type = guess_type(file_name)[0]
        
        if not mime_type:
            extension = file_name.lower().split('.')[-1] if '.' in file_name else ''
            
            video_mime_types = {
                'mp4': 'video/mp4',
                'm4v': 'video/mp4',
                'webm': 'video/webm',
                'ogv': 'video/ogg',
                'ogg': 'video/ogg',
                'mkv': 'video/x-matroska',
                'avi': 'video/x-msvideo',
                'mov': 'video/quicktime',
                'wmv': 'video/x-ms-wmv',
                'flv': 'video/x-flv',
                'm3u8': 'application/x-mpegURL',
                'ts': 'video/mp2t',
                '3gp': 'video/3gpp',
                '3g2': 'video/3gpp2',
                'mpg': 'video/mpeg',
                'mpeg': 'video/mpeg',
                'mts': 'video/mp2t',
                'm2ts': 'video/mp2t',
                'vob': 'video/dvd',
                'f4v': 'video/x-f4v',
                'mxf': 'application/mxf'
            }
            
            mime_type = video_mime_types.get(extension, 'application/octet-stream')
    
    return file_name, file_size, mime_type