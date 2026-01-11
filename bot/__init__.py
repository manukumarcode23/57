from telethon import TelegramClient
from logging import getLogger
from logging.config import dictConfig
from .config import Telegram, LOGGER_CONFIG_JSON

dictConfig(LOGGER_CONFIG_JSON)

# Apply log sanitization to prevent credential leakage
from bot.modules.log_sanitizer import apply_sensitive_data_filter
apply_sensitive_data_filter()

version = 1.6
logger = getLogger('bot')

TelegramBot = TelegramClient(
    session='bot',
    api_id=Telegram.API_ID,
    api_hash=Telegram.API_HASH
)