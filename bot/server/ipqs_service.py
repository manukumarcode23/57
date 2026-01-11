import aiohttp
import asyncio
from logging import getLogger
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone

logger = getLogger('uvicorn')

IPQS_PROXY_DETECTION_URL = "https://www.ipqualityscore.com/api/json/ip/{api_key}/{ip}"


async def get_available_ipqs_key():
    """Get an available IPQS API key from the database with usage tracking"""
    from bot.database import AsyncSessionLocal
    from bot.models import IPQSApiKey
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(IPQSApiKey)
            .where(IPQSApiKey.is_active == True)
            .order_by(IPQSApiKey.usage_count.asc(), IPQSApiKey.last_used_at.asc().nullsfirst())
        )
        keys = result.scalars().all()
        
        for key in keys:
            if key.usage_count < key.request_limit:
                return key.id, key.api_key
        
        return None, None


async def increment_ipqs_key_usage(key_id: int):
    """Increment usage count for an IPQS API key"""
    from bot.database import AsyncSessionLocal
    from bot.models import IPQSApiKey
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(IPQSApiKey).where(IPQSApiKey.id == key_id)
        )
        key = result.scalar_one_or_none()
        
        if key:
            key.usage_count += 1
            key.last_used_at = datetime.now(timezone.utc)
            await db_session.commit()

@dataclass
class IPQSResult:
    success: bool
    fraud_score: int = 0
    is_proxy: bool = False
    is_vpn: bool = False
    is_tor: bool = False
    is_bot: bool = False
    recent_abuse: bool = False
    is_crawler: bool = False
    country_code: Optional[str] = None
    city: Optional[str] = None
    isp: Optional[str] = None
    message: Optional[str] = None
    request_id: Optional[str] = None
    
    @property
    def is_valid_impression(self) -> bool:
        if self.is_bot or self.is_crawler:
            return False
        if self.is_vpn:
            return False
        if self.is_proxy:
            return False
        if self.is_tor:
            return False
        if self.fraud_score >= 85:
            return False
        if self.recent_abuse:
            return False
        return True
    
    @property
    def rejection_reason(self) -> Optional[str]:
        if self.is_bot:
            return "Bot detected"
        if self.is_crawler:
            return "Crawler detected"
        if self.is_vpn:
            return "VPN detected"
        if self.is_proxy:
            return "Proxy detected"
        if self.is_tor:
            return "Tor network detected"
        if self.fraud_score >= 85:
            return f"High fraud score: {self.fraud_score}"
        if self.recent_abuse:
            return "Recent abuse detected"
        return None


async def verify_ip_quality(api_key: str, ip_address: str, user_agent: Optional[str] = None) -> IPQSResult:
    if not api_key or not ip_address:
        return IPQSResult(success=False, message="API key or IP address missing")
    
    if ip_address in ['127.0.0.1', 'localhost', '0.0.0.0']:
        return IPQSResult(success=True, fraud_score=0, message="Local IP, skipping verification")
    
    url = IPQS_PROXY_DETECTION_URL.format(api_key=api_key, ip=ip_address)
    
    params = {
        'strictness': 1,
        'allow_public_access_points': 'true',
        'fast': 'true',
        'lighter_penalties': 'true'
    }
    
    if user_agent:
        params['user_agent'] = user_agent
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    logger.error(f"IPQS API error: HTTP {response.status}")
                    return IPQSResult(success=False, message=f"HTTP error: {response.status}")
                
                data = await response.json()
                
                if not data.get('success', False):
                    error_msg = data.get('message', 'Unknown error')
                    logger.error(f"IPQS API error: {error_msg}")
                    return IPQSResult(success=False, message=error_msg)
                
                result = IPQSResult(
                    success=True,
                    fraud_score=data.get('fraud_score', 0),
                    is_proxy=data.get('proxy', False),
                    is_vpn=data.get('vpn', False),
                    is_tor=data.get('tor', False),
                    is_bot=data.get('bot_status', False),
                    recent_abuse=data.get('recent_abuse', False),
                    is_crawler=data.get('is_crawler', False),
                    country_code=data.get('country_code'),
                    city=data.get('city'),
                    isp=data.get('ISP'),
                    request_id=data.get('request_id')
                )
                
                logger.info(f"IPQS verification for {ip_address}: fraud_score={result.fraud_score}, bot={result.is_bot}, vpn={result.is_vpn}, proxy={result.is_proxy}, valid={result.is_valid_impression}")
                
                return result
                
    except asyncio.TimeoutError:
        logger.error(f"IPQS API timeout for IP: {ip_address}")
        return IPQSResult(success=False, message="Request timeout")
    except Exception as e:
        logger.error(f"IPQS API error: {str(e)}")
        return IPQSResult(success=False, message=str(e))


async def get_ipqs_secret_key_script(secret_key: str) -> str:
    if not secret_key:
        return ""
    return f'<script src="https://www.ipqscdn.com/api/{secret_key}/learn.js"></script>'
