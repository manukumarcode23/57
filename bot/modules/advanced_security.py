"""
Advanced Security Module for Ultra-Secure File Upload Protection
Implements multi-layer security validation to prevent any bypass attempts
"""

import io
import logging
import hashlib
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from PIL import Image
import struct

logger = logging.getLogger('bot.security.advanced')

# File signature (magic numbers) database for deep validation
FILE_SIGNATURES = {
    # Video formats
    'video/mp4': [
        b'\x00\x00\x00\x18ftypmp4',
        b'\x00\x00\x00\x1cftypisom',
        b'\x00\x00\x00\x20ftypisom',
        b'\x00\x00\x00\x1cftypM4V',
        b'ftyp',
    ],
    'video/x-matroska': [b'\x1a\x45\xdf\xa3'],
    'video/webm': [b'\x1a\x45\xdf\xa3'],
    'video/avi': [b'RIFF', b'AVI '],
    'video/quicktime': [b'ftypqt'],
    
    # Image formats
    'image/jpeg': [b'\xff\xd8\xff'],
    'image/png': [b'\x89PNG\r\n\x1a\n'],
    'image/gif': [b'GIF87a', b'GIF89a'],
    'image/webp': [b'RIFF', b'WEBP'],
    'image/bmp': [b'BM'],
    
    # Archive formats
    'application/zip': [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'],
    'application/x-rar': [b'Rar!\x1a\x07'],
    'application/x-7z-compressed': [b'7z\xbc\xaf\x27\x1c'],
    
    # APK (which is a ZIP)
    'application/vnd.android.package-archive': [b'PK\x03\x04'],
    
    # PDF
    'application/pdf': [b'%PDF-'],
}

# Maximum file sizes per type (in bytes)
MAX_FILE_SIZES = {
    'image': 20 * 1024 * 1024,      # 20 MB for images
    'video': 2 * 1024 * 1024 * 1024, # 2 GB for videos
    'archive': 500 * 1024 * 1024,    # 500 MB for archives
    'document': 50 * 1024 * 1024,    # 50 MB for documents
    'apk': 500 * 1024 * 1024,        # 500 MB for APKs
    'default': 100 * 1024 * 1024,    # 100 MB default
}

# Minimum file sizes to prevent empty/corrupt files (in bytes)
MIN_FILE_SIZES = {
    'image': 100,           # 100 bytes minimum
    'video': 1024,          # 1 KB minimum
    'archive': 100,         # 100 bytes minimum
    'document': 50,         # 50 bytes minimum
    'apk': 1024,           # 1 KB minimum
    'default': 50,          # 50 bytes default
}

# Suspicious patterns that might indicate malicious content
SUSPICIOUS_PATTERNS = [
    b'<script',
    b'javascript:',
    b'eval(',
    b'base64,',
    b'data:text/html',
    b'<?php',
    b'#!/bin/sh',
    b'#!/bin/bash',
    b'cmd.exe',
    b'powershell',
]

# Blacklisted hash database (known malware signatures)
BLACKLISTED_HASHES = set([
    # Add known malicious file hashes here
    # Example: 'd41d8cd98f00b204e9800998ecf8427e'
])


def validate_magic_number(file_bytes: bytes, mime_type: str) -> Tuple[bool, str]:
    """
    Validate file using magic number (file signature) verification
    This prevents file extension spoofing attacks
    
    Args:
        file_bytes: First 512 bytes of the file
        mime_type: Expected MIME type
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(file_bytes) < 4:
        return False, "File is too small or corrupted"
    
    # Get expected signatures for this MIME type
    expected_signatures = FILE_SIGNATURES.get(mime_type, [])
    
    if not expected_signatures:
        # If we don't have signature for this type, allow it but log
        logger.warning(f"No magic number signature defined for MIME type: {mime_type}")
        return True, ""
    
    # Check if file starts with any of the expected signatures
    for signature in expected_signatures:
        if file_bytes.startswith(signature) or signature in file_bytes[:512]:
            return True, ""
    
    logger.error(f"Magic number validation failed for {mime_type}. File signature mismatch.")
    return False, f"File content does not match declared type. Possible file extension spoofing detected."


def scan_for_suspicious_content(file_bytes: bytes) -> Tuple[bool, str]:
    """
    Scan file content for suspicious patterns that might indicate malicious code
    
    Args:
        file_bytes: File content to scan
        
    Returns:
        Tuple of (is_safe, error_message)
    """
    # Scan first 10MB of file for performance
    scan_chunk = file_bytes[:10 * 1024 * 1024]
    
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in scan_chunk:
            logger.error(f"Suspicious pattern detected in file: {pattern}")
            return False, "File contains suspicious content and cannot be uploaded"
    
    return True, ""


def validate_file_hash(file_bytes: bytes) -> Tuple[bool, str]:
    """
    Check file hash against blacklist of known malicious files
    
    Args:
        file_bytes: Complete file content
        
    Returns:
        Tuple of (is_safe, error_message)
    """
    file_hash = hashlib.md5(file_bytes).hexdigest()
    
    if file_hash in BLACKLISTED_HASHES:
        logger.critical(f"Blacklisted file hash detected: {file_hash}")
        return False, "This file has been identified as malicious and cannot be uploaded"
    
    return True, ""


def validate_image_integrity(file_bytes: bytes) -> Tuple[bool, str]:
    """
    Validate image file integrity and check for embedded malicious content
    
    Args:
        file_bytes: Image file content
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        img = Image.open(io.BytesIO(file_bytes))
        
        # Verify image can be loaded
        img.verify()
        
        # Check image dimensions (prevent decompression bombs)
        img = Image.open(io.BytesIO(file_bytes))  # Reopen after verify
        width, height = img.size
        
        # Maximum 50 megapixels
        if width * height > 50_000_000:
            return False, "Image dimensions are too large (possible decompression bomb attack)"
        
        # Minimum dimensions (1x1 is suspicious)
        if width < 10 or height < 10:
            return False, "Image dimensions are too small (possible corrupted file)"
        
        # Check for suspicious aspect ratios
        aspect_ratio = max(width, height) / min(width, height)
        if aspect_ratio > 100:
            return False, "Image has suspicious aspect ratio"
        
        return True, ""
        
    except Exception as e:
        logger.error(f"Image validation failed: {e}")
        return False, "Image file is corrupted or invalid"


def validate_file_size(file_size: int, file_category: str) -> Tuple[bool, str]:
    """
    Validate file size against category-specific limits
    
    Args:
        file_size: Size of file in bytes
        file_category: Category of file (image, video, archive, etc.)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    max_size = MAX_FILE_SIZES.get(file_category, MAX_FILE_SIZES['default'])
    min_size = MIN_FILE_SIZES.get(file_category, MIN_FILE_SIZES['default'])
    
    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        return False, f"File size exceeds maximum allowed size of {max_mb:.1f} MB for {file_category} files"
    
    if file_size < min_size:
        return False, f"File size is too small. Possible corrupted or empty file."
    
    return True, ""


def get_file_category(mime_type: str) -> str:
    """
    Determine file category from MIME type
    
    Args:
        mime_type: MIME type of file
        
    Returns:
        File category string
    """
    if mime_type.startswith('image/'):
        return 'image'
    elif mime_type.startswith('video/'):
        return 'video'
    elif 'zip' in mime_type or 'rar' in mime_type or '7z' in mime_type or 'tar' in mime_type:
        return 'archive'
    elif mime_type == 'application/vnd.android.package-archive':
        return 'apk'
    elif 'pdf' in mime_type or 'document' in mime_type:
        return 'document'
    else:
        return 'default'


async def ultra_secure_validation(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    file_size: int,
    publisher_id: int,
    skip_size_limits: bool = False
) -> Tuple[bool, str]:
    """
    Perform ultra-secure multi-layer validation on uploaded file
    This is the main security checkpoint - all validations must pass
    
    Args:
        file_bytes: First 512 bytes (or more for deep scan) of file
        filename: Original filename
        mime_type: MIME type
        file_size: File size in bytes
        publisher_id: Publisher ID for logging
        skip_size_limits: If True, skip file size validation (for Telegram unlimited uploads)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    logger.info(f"Starting ultra-secure validation for file: {filename}, publisher: {publisher_id}, skip_size_limits: {skip_size_limits}")
    
    # Layer 1: File size validation (skip for Telegram uploads if requested)
    file_category = get_file_category(mime_type)  # Always initialize file_category
    
    if not skip_size_limits:
        is_valid, error = validate_file_size(file_size, file_category)
        if not is_valid:
            logger.warning(f"File size validation failed: {filename} - {error}")
            return False, error
    else:
        logger.info(f"Skipping file size validation for unlimited Telegram upload: {filename}")
    
    # Layer 2: Magic number validation (prevent extension spoofing)
    is_valid, error = validate_magic_number(file_bytes, mime_type)
    if not is_valid:
        logger.error(f"Magic number validation failed: {filename} - {error}")
        return False, error
    
    # Layer 3: Suspicious content scanning
    is_valid, error = scan_for_suspicious_content(file_bytes)
    if not is_valid:
        logger.critical(f"Suspicious content detected: {filename} - {error}")
        return False, error
    
    # Layer 4: Image-specific validation (if applicable)
    if file_category == 'image':
        is_valid, error = validate_image_integrity(file_bytes)
        if not is_valid:
            logger.error(f"Image integrity validation failed: {filename} - {error}")
            return False, error
    
    # Layer 5: Hash-based malware check (if full file available)
    if len(file_bytes) == file_size:  # Full file available
        is_valid, error = validate_file_hash(file_bytes)
        if not is_valid:
            logger.critical(f"Malicious file hash detected: {filename} - {error}")
            return False, error
    
    logger.info(f"Ultra-secure validation passed: {filename}")
    return True, ""


def strip_metadata(image_bytes: bytes) -> bytes:
    """
    Strip EXIF and other metadata from images for privacy and security
    
    Args:
        image_bytes: Original image bytes
        
    Returns:
        Image bytes with metadata stripped
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Create new image without EXIF data
        image_without_exif = Image.new(img.mode, img.size)
        image_without_exif.putdata(img.getdata())
        
        # Save to bytes
        output = io.BytesIO()
        image_without_exif.save(output, format=img.format)
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Metadata stripping failed: {e}")
        return image_bytes  # Return original if stripping fails
