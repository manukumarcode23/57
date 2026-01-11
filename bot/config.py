from os import environ as env
from dotenv import load_dotenv
from pathlib import Path

# Load .env file from the project root
# Preserve critical environment variables that should not be overridden by .env
_preserved_vars = {
    "DATABASE_URL": env.get("DATABASE_URL"),
    "PGHOST": env.get("PGHOST"),
    "PGPORT": env.get("PGPORT"),
    "PGUSER": env.get("PGUSER"),
    "PGPASSWORD": env.get("PGPASSWORD"),
    "PGDATABASE": env.get("PGDATABASE"),
}

# Load .env file if it exists (but don't override Replit Secrets)
_env_path = Path(__file__).parent.parent / '.env'
if _env_path.exists():
    load_dotenv(_env_path, override=False)
    
    # Restore preserved variables if they were overridden with empty values
    for key, value in _preserved_vars.items():
        if value and not env.get(key):
            env[key] = value

# REQUIRED CONFIGURATION
# Add these environment variables:
# - TELEGRAM_API_ID: Your Telegram API ID
# - TELEGRAM_API_HASH: Your Telegram API Hash
# - TELEGRAM_BOT_TOKEN: Your bot token from @BotFather
# - TELEGRAM_CHANNEL_ID: Channel ID for file storage
# - OWNER_ID: Bot owner's Telegram user ID
# - TELEGRAM_BOT_USERNAME: Bot username without @
# - BASE_URL: Public URL of your deployment (e.g., https://yourdomain.com)
# - DATABASE_URL: PostgreSQL database connection string

class Telegram:
    # Configuration - reads from environment variables with fallback values
    
    _api_id_str = env.get("TELEGRAM_API_ID") or "25090660"
    API_ID = int(_api_id_str)
    
    API_HASH = env.get("TELEGRAM_API_HASH") or "58fd3b352d60d49f6d145364c6791c1b"
    
    _owner_id_str = env.get("OWNER_ID") or "8391217905"
    OWNER_ID = int(_owner_id_str)
    
    allowed_user_ids_str = env.get("ALLOWED_USER_IDS")
    ALLOWED_USER_IDS = [int(x.strip()) for x in allowed_user_ids_str.split(",")] if allowed_user_ids_str else []
    
    BOT_USERNAME = env.get("TELEGRAM_BOT_USERNAME") or "Tertbbbbbot"
    
    BOT_TOKEN = env.get("TELEGRAM_BOT_TOKEN") or "8323648359:AAHHeBUUG-RuJZhDPmuOlsAYGwepIUQ1mGk"
    
    _channel_id_str = env.get("TELEGRAM_CHANNEL_ID") or "-1002976875407"
    CHANNEL_ID = int(_channel_id_str)
    
    _secret_len_str = env.get("SECRET_CODE_LENGTH") or "12"
    SECRET_CODE_LENGTH = int(_secret_len_str) if _secret_len_str else 12

class Server:
    # BASE_URL configuration
    BASE_URL = env.get("BASE_URL") or "https://69ff6d00-87fd-4870-b125-9fd77c78e4fc-00-6achlais3yja.sisko.replit.dev"
    
    # External Link Generation API
    EXTERNAL_LINK_GEN_URL = env.get("EXTERNAL_LINK_GEN_URL")
    
    CALLBACK_API_URL = env.get("CALLBACK_API_URL")
    BIND_ADDRESS = env.get("BIND_ADDRESS") or "0.0.0.0"
    _port_str = env.get("PORT") or "5000"
    PORT = int(_port_str) if _port_str else 5000
    
    _max_file_size_str = env.get("MAX_FILE_SIZE_MB") or "2048"
    MAX_FILE_SIZE = int(_max_file_size_str) * 1024 * 1024  # Convert MB to bytes
    
    _upload_rate_limit_str = env.get("UPLOAD_RATE_LIMIT") or "10"
    UPLOAD_RATE_LIMIT = int(_upload_rate_limit_str)
    _upload_rate_window_str = env.get("UPLOAD_RATE_WINDOW") or "3600"
    UPLOAD_RATE_WINDOW = int(_upload_rate_window_str)

# LOGGING CONFIGURATION
LOG_FILENAME = env.get("LOG_FILENAME") or "event-log.txt"
LOG_MAX_BYTES = int(env.get("LOG_MAX_BYTES") or "10485760")  # 10MB default
LOG_BACKUP_COUNT = int(env.get("LOG_BACKUP_COUNT") or "5")  # Keep 5 backup files

LOGGER_CONFIG_JSON = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '[%(asctime)s][%(name)s][%(levelname)s] -> %(message)s',
            'datefmt': '%d/%m/%Y %H:%M:%S'
        },
    },
    'handlers': {
        'file_handler': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_FILENAME,
            'maxBytes': LOG_MAX_BYTES,
            'backupCount': LOG_BACKUP_COUNT,
            'formatter': 'default'
        },
        'stream_handler': {
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        }
    },
    'loggers': {
        'uvicorn': {
            'level': 'INFO',
            'handlers': ['file_handler', 'stream_handler']
        },
        'uvicorn.error': {
            'level': 'WARNING',
            'handlers': ['file_handler', 'stream_handler']
        },
        'bot': {
            'level': 'INFO',
            'handlers': ['file_handler', 'stream_handler']
        }
    }
}