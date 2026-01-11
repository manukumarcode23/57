"""
File validation module for security and file type checking
"""

import logging
import mimetypes
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger('bot.security')

# Whitelist of allowed MIME types
ALLOWED_MIME_TYPES = {
    # Video formats
    'video/mp4', 'video/mpeg', 'video/quicktime', 'video/x-msvideo',
    'video/x-matroska', 'video/webm', 'video/3gpp', 'video/x-flv',
    
    # Archive formats
    'application/zip', 'application/x-zip-compressed',
    'application/x-rar-compressed', 'application/x-7z-compressed',
    'application/gzip', 'application/x-tar',
    
    # Android packages
    'application/vnd.android.package-archive',
    
    # Documents
    'application/pdf', 'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    
    # Images
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp',
    
    # Audio
    'audio/mpeg', 'audio/mp4', 'audio/wav', 'audio/ogg', 'audio/webm',
    
    # Text
    'text/plain', 'text/csv',
    
    # Generic binary (for compatibility)
    'application/octet-stream',
}

# File extensions whitelist
ALLOWED_EXTENSIONS = {
    # Video
    '.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.3gp', '.m4v',
    
    # Archive
    '.zip', '.rar', '.7z', '.tar', '.gz', '.tgz',
    
    # Android
    '.apk', '.xapk',
    
    # Documents
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.csv',
    
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
    
    # Audio
    '.mp3', '.m4a', '.wav', '.ogg', '.flac',
}

# Dangerous file extensions to explicitly block
BLOCKED_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.com', '.scr', '.pif', '.vbs', '.js', 
    '.jar', '.dll', '.msi', '.app', '.deb', '.rpm', '.sh', '.ps1',
}


def validate_file_type(filename: str, mime_type: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validate file type against whitelist
    
    Args:
        filename: Name of the file
        mime_type: MIME type of the file (if known)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not filename:
        return False, "Filename is required"
    
    # Get file extension
    file_ext = Path(filename).suffix.lower()
    
    # Check for blocked extensions first
    if file_ext in BLOCKED_EXTENSIONS:
        logger.warning(f"Blocked file upload attempt: {filename} (extension: {file_ext})")
        return False, f"File type '{file_ext}' is not allowed for security reasons"
    
    # Check extension whitelist
    if file_ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"Rejected file with unknown extension: {filename} (extension: {file_ext})")
        return False, f"File extension '{file_ext}' is not supported. Allowed types: video, zip, apk, pdf, images"
    
    if not mime_type:
        # If MIME type not provided, try to guess from filename
        mime_type = get_safe_mime_type(filename)
    
    # Normalize MIME type (remove parameters)
    base_mime = mime_type.split(';')[0].strip().lower()
    
    if base_mime not in ALLOWED_MIME_TYPES:
        logger.warning(f"Rejected file with invalid MIME type: {filename} (MIME: {base_mime})")
        return False, f"File type '{base_mime}' is not supported"
    
    return True, ""


def get_safe_mime_type(filename: str) -> str:
    """
    Get MIME type from filename with fallback
    
    Args:
        filename: Name of the file
        
    Returns:
        MIME type string
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or 'application/octet-stream'


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent directory traversal attacks
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove any path components
    filename = Path(filename).name
    
    # Remove any null bytes
    filename = filename.replace('\x00', '')
    
    # Limit filename length
    if len(filename) > 255:
        name, ext = Path(filename).stem, Path(filename).suffix
        filename = name[:255 - len(ext)] + ext
    
    return filename
