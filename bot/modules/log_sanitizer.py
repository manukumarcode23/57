import re
import logging

class SensitiveDataFilter(logging.Filter):
    """
    Logging filter to sanitize sensitive data from log messages
    Prevents credential leakage in logs and error messages
    """
    
    PATTERNS = [
        # Telegram bot token pattern: bot1234567890:ABCdefGHI...
        (re.compile(r'bot[0-9]{8,10}:[a-zA-Z0-9_-]{35}'), 'BOT_TOKEN_REDACTED'),
        # API hash (32 character hex)
        (re.compile(r'\b[0-9a-fA-F]{32}\b'), 'API_HASH_REDACTED'),
        # API ID (6-10 digits)
        (re.compile(r'\bapi_id[\'\":\s]+[0-9]{6,10}'), 'api_id: API_ID_REDACTED'),
        # Database connection strings
        (re.compile(r'postgresql://[^@]+@[^\s]+'), 'postgresql://USER:PASS_REDACTED@HOST/DB'),
        (re.compile(r'postgres://[^@]+@[^\s]+'), 'postgres://USER:PASS_REDACTED@HOST/DB'),
        # Generic password patterns
        (re.compile(r'password[\'\":\s=]+[^\s\'"]+', re.IGNORECASE), 'password: PASSWORD_REDACTED'),
        (re.compile(r'secret[\'\":\s=]+[^\s\'"]+', re.IGNORECASE), 'secret: SECRET_REDACTED'),
    ]
    
    def filter(self, record):
        """
        Filter log record to remove sensitive data
        
        Args:
            record: LogRecord to filter
            
        Returns:
            True (always allow the log, but with sanitized data)
        """
        try:
            # Get the formatted message
            message = record.getMessage()
            
            # Apply all sanitization patterns
            for pattern, replacement in self.PATTERNS:
                message = pattern.sub(replacement, message)
            
            # Update the record
            record.msg = message
            record.args = ()
            
        except Exception:
            # Don't let sanitization break logging
            pass
        
        return True


def apply_sensitive_data_filter():
    """
    Apply the sensitive data filter to all loggers
    Should be called during application initialization
    """
    # Add filter to root logger (affects all loggers)
    logging.root.addFilter(SensitiveDataFilter())
    
    # Also add to all existing handlers
    for handler in logging.root.handlers:
        handler.addFilter(SensitiveDataFilter())
