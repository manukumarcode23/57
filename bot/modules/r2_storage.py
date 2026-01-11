import boto3
import logging
import os
from bot.database import AsyncSessionLocal
from bot.models import CloudflareR2Settings, Settings
from sqlalchemy import select

logger = logging.getLogger('bot.modules.r2_storage')

async def get_active_r2_settings():
    """Get the active Cloudflare R2 settings from the database"""
    async with AsyncSessionLocal() as session:
        # First check if R2 is globally enabled
        settings_result = await session.execute(select(Settings))
        global_settings = settings_result.scalar_one_or_none()
        
        if not global_settings or not global_settings.r2_storage_enabled:
            return None
            
        # Then find an active R2 bucket configuration
        result = await session.execute(
            select(CloudflareR2Settings).where(CloudflareR2Settings.is_active == True)
        )
        return result.scalar_one_or_none()

async def upload_file_to_r2(file_path, object_name):
    """Upload a file to Cloudflare R2"""
    r2_settings = await get_active_r2_settings()
    if not r2_settings:
        return None

    try:
        import boto3
        from botocore.config import Config
        
        # Use a config to set a reasonable timeout
        config = Config(
            connect_timeout=5,
            read_timeout=10,
            retries={'max_attempts': 2}
        )
        
        s3_client = boto3.client(
            's3',
            endpoint_url=r2_settings.endpoint_url,
            aws_access_key_id=r2_settings.access_key_id,
            aws_secret_access_key=r2_settings.secret_access_key,
            region_name=r2_settings.region,
            config=config
        )
        
        # Run upload in a thread pool to avoid blocking the event loop
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            lambda: s3_client.upload_file(file_path, r2_settings.bucket_name, object_name)
        )
        
        logger.info(f"Successfully uploaded {file_path} to R2 as {object_name}")
        return object_name
    except Exception as e:
        logger.error(f"Error uploading to R2: {e}")
        return None

async def delete_from_r2(object_name):
    """Delete an object from Cloudflare R2"""
    r2_settings = await get_active_r2_settings()
    if not r2_settings:
        return False

    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=r2_settings.endpoint_url,
            aws_access_key_id=r2_settings.access_key_id,
            aws_secret_access_key=r2_settings.secret_access_key,
            region_name=r2_settings.region
        )
        
        s3_client.delete_object(Bucket=r2_settings.bucket_name, Key=object_name)
        return True
    except Exception as e:
        logger.error(f"Error deleting from R2: {e}")
        return False

async def get_r2_download_url(object_key, expires_in=7200):
    """Generate a temporary pre-signed download URL for an R2 object"""
    r2_settings = await get_active_r2_settings()
    if not r2_settings or not object_key:
        return None
    
    try:
        import boto3
        from botocore.config import Config
        
        # Configure the S3 client for R2
        s3_client = boto3.client(
            's3',
            endpoint_url=r2_settings.endpoint_url,
            aws_access_key_id=r2_settings.access_key_id,
            aws_secret_access_key=r2_settings.secret_access_key,
            region_name=r2_settings.region,
            config=Config(signature_version='s3v4')
        )
        
        # Generate the pre-signed URL
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': r2_settings.bucket_name,
                'Key': object_key
            },
            ExpiresIn=expires_in
        )
        
        # If we have a custom domain, replace the default R2 hostname with it
        custom_domain = getattr(r2_settings, 'custom_domain', None)
        if custom_domain:
            # The presigned URL includes the bucket and endpoint. 
            # We replace the base parts but keep the query parameters for authentication
            import re
            url = re.sub(r'https://[^/?]+', f'https://{custom_domain}', url)
            
        return url
    except Exception as e:
        logger.error(f"Error generating presigned R2 URL: {e}")
        return None
