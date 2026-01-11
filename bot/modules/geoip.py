import httpx
import logging
import json
from typing import Optional, Tuple

logger = logging.getLogger('bot.geoip')

async def get_location_from_ip(ip_address: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Get country code, country name, and region from IP address
    Returns: (country_code, country_name, region)
    
    Uses ip-api.com HTTPS service (45 requests/minute, no API key required)
    Note: HTTPS is only available for paid plans on ip-api.com. Using free HTTPS alternative.
    """
    if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1', '0.0.0.0']:
        return 'Unknown', 'Unknown', 'Unknown'
    
    parts = ip_address.split('.')
    if len(parts) == 4:
        try:
            first_octet = int(parts[0])
            second_octet = int(parts[1])
            
            if first_octet == 10:
                logger.debug(f"Private IP (10.x) detected: {ip_address}")
                return 'Unknown', 'Unknown', 'Unknown'
            elif first_octet == 172 and 16 <= second_octet <= 31:
                logger.debug(f"Private IP (172.16-31.x) detected: {ip_address}")
                return 'Unknown', 'Unknown', 'Unknown'
            elif first_octet == 192 and second_octet == 168:
                logger.debug(f"Private IP (192.168.x) detected: {ip_address}")
                return 'Unknown', 'Unknown', 'Unknown'
        except (ValueError, IndexError):
            pass
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f'https://ipapi.co/{ip_address}/json/',
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'error' not in data:
                        country_code = data.get('country_code', 'Unknown')
                        country_name = data.get('country_name', 'Unknown')
                        region = data.get('region', 'Unknown')
                        
                        logger.debug(f"IP {ip_address} -> {country_code}, {country_name}, {region}")
                        return country_code, country_name, region
                    else:
                        logger.warning(f"IP geolocation failed for {ip_address}: {data.get('reason', 'Unknown error')}")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Invalid JSON response from IP API for {ip_address}: {e}. Response: {response.text[:200]}")
            else:
                logger.warning(f"IP geolocation API returned status {response.status_code} for {ip_address}")
    except httpx.TimeoutException:
        logger.error(f"Timeout while getting location for IP {ip_address}")
    except httpx.RequestError as e:
        logger.error(f"Network error getting location for IP {ip_address}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting location for IP {ip_address}: {e}")
    
    return 'Unknown', 'Unknown', 'Unknown'

def get_location_from_ip_sync(ip_address: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Synchronous version of get_location_from_ip
    Returns: (country_code, country_name, region)
    Uses HTTPS for secure communication
    """
    if not ip_address or ip_address in ['127.0.0.1', 'localhost', '::1', '0.0.0.0']:
        return 'Unknown', 'Unknown', 'Unknown'
    
    parts = ip_address.split('.')
    if len(parts) == 4:
        try:
            first_octet = int(parts[0])
            second_octet = int(parts[1])
            
            if first_octet == 10:
                logger.debug(f"Private IP (10.x) detected: {ip_address}")
                return 'Unknown', 'Unknown', 'Unknown'
            elif first_octet == 172 and 16 <= second_octet <= 31:
                logger.debug(f"Private IP (172.16-31.x) detected: {ip_address}")
                return 'Unknown', 'Unknown', 'Unknown'
            elif first_octet == 192 and second_octet == 168:
                logger.debug(f"Private IP (192.168.x) detected: {ip_address}")
                return 'Unknown', 'Unknown', 'Unknown'
        except (ValueError, IndexError):
            pass
    
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                f'https://ipapi.co/{ip_address}/json/',
                headers={'User-Agent': 'Mozilla/5.0'}
            )
        
            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'error' not in data:
                        country_code = data.get('country_code', 'Unknown')
                        country_name = data.get('country_name', 'Unknown')
                        region = data.get('region', 'Unknown')
                        
                        logger.debug(f"IP {ip_address} -> {country_code}, {country_name}, {region}")
                        return country_code, country_name, region
                    else:
                        logger.warning(f"IP geolocation failed for {ip_address}: {data.get('reason', 'Unknown error')}")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Invalid JSON response from IP API for {ip_address}: {e}. Response: {response.text[:200]}")
            else:
                logger.warning(f"IP geolocation API returned status {response.status_code} for {ip_address}")
    except httpx.TimeoutException:
        logger.error(f"Timeout while getting location for IP {ip_address}")
    except httpx.RequestError as e:
        logger.error(f"Network error getting location for IP {ip_address}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error getting location for IP {ip_address}: {e}")
    
    return 'Unknown', 'Unknown', 'Unknown'
