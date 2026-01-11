"""
Device Detection and Fingerprinting Module
Detects device types, operating systems, browsers, and generates device fingerprints
"""

import hashlib
import re
from typing import Dict, Optional, Tuple
from user_agents import parse


def parse_user_agent(user_agent: str) -> Dict[str, Optional[str]]:
    """
    Parse user agent string to extract device information
    
    Returns dict with:
    - device_type: Android, PC, Laptop, Tablet, Mobile, Emulator, etc.
    - device_name: Specific device model or brand
    - operating_system: OS name and version
    - browser_name: Browser name
    - browser_version: Browser version
    """
    if not user_agent:
        return {
            'device_type': 'Unknown',
            'device_name': 'Unknown',
            'operating_system': 'Unknown',
            'browser_name': 'Unknown',
            'browser_version': 'Unknown'
        }
    
    try:
        ua = parse(user_agent)
        
        device_type = detect_device_type(user_agent, ua)
        device_name = extract_device_name(user_agent, ua)
        operating_system = f"{ua.os.family} {ua.os.version_string}" if ua.os.family else "Unknown"
        browser_name = ua.browser.family if ua.browser.family else "Unknown"
        browser_version = ua.browser.version_string if ua.browser.version_string else "Unknown"
        
        return {
            'device_type': device_type,
            'device_name': device_name,
            'operating_system': operating_system,
            'browser_name': browser_name,
            'browser_version': browser_version
        }
    
    except Exception:
        return {
            'device_type': 'Unknown',
            'device_name': 'Unknown',
            'operating_system': 'Unknown',
            'browser_name': 'Unknown',
            'browser_version': 'Unknown'
        }


def detect_device_type(user_agent: str, ua) -> str:
    """Detect specific device type including emulators"""
    user_agent_lower = user_agent.lower()
    
    # Check for emulators first
    emulator_signatures = [
        'generic', 'sdk_gphone', 'android sdk', 'emulator',
        'vbox', 'virtualbox', 'vmware', 'genymotion',
        'bluestacks', 'noxplayer', 'memu', 'ldplayer'
    ]
    
    for signature in emulator_signatures:
        if signature in user_agent_lower:
            return 'Emulator'
    
    # Check for specific device types
    if ua.is_mobile:
        if ua.is_tablet:
            return 'Tablet'
        elif 'android' in user_agent_lower:
            return 'Android Phone'
        elif 'iphone' in user_agent_lower:
            return 'iPhone'
        else:
            return 'Mobile Device'
    
    if ua.is_tablet:
        if 'ipad' in user_agent_lower:
            return 'iPad'
        else:
            return 'Tablet'
    
    if ua.is_pc:
        if 'macintosh' in user_agent_lower or 'mac os' in user_agent_lower:
            return 'Mac'
        elif 'windows' in user_agent_lower:
            return 'Windows PC'
        elif 'linux' in user_agent_lower:
            return 'Linux PC'
        else:
            return 'Desktop'
    
    # Check for bots/crawlers
    bot_signatures = ['bot', 'crawler', 'spider', 'scraper', 'headless']
    for signature in bot_signatures:
        if signature in user_agent_lower:
            return 'Bot/Crawler'
    
    return 'Unknown Device'


def extract_device_name(user_agent: str, ua) -> str:
    """Extract specific device model or brand name"""
    
    # Try to get from user-agents library
    if ua.device.family and ua.device.family != 'Other':
        device_info = ua.device.family
        if ua.device.brand:
            device_info = f"{ua.device.brand} {device_info}"
        if ua.device.model:
            device_info = f"{device_info} {ua.device.model}"
        return device_info.strip()
    
    # Manual extraction for common patterns
    user_agent_lower = user_agent.lower()
    
    # Samsung devices
    samsung_match = re.search(r'(sm-[a-z0-9]+|galaxy [a-z0-9 ]+)', user_agent_lower)
    if samsung_match:
        return f"Samsung {samsung_match.group(1).upper()}"
    
    # Xiaomi/Redmi devices
    xiaomi_match = re.search(r'(redmi [a-z0-9 ]+|mi [a-z0-9 ]+)', user_agent_lower)
    if xiaomi_match:
        return f"Xiaomi {xiaomi_match.group(1).title()}"
    
    # OnePlus devices
    oneplus_match = re.search(r'(oneplus [a-z0-9]+)', user_agent_lower)
    if oneplus_match:
        return oneplus_match.group(1).title()
    
    # Oppo devices
    oppo_match = re.search(r'(oppo [a-z0-9]+|cph[0-9]+)', user_agent_lower)
    if oppo_match:
        return f"Oppo {oppo_match.group(1).upper()}"
    
    # Vivo devices
    vivo_match = re.search(r'(vivo [a-z0-9]+|v[0-9]+)', user_agent_lower)
    if vivo_match:
        return f"Vivo {vivo_match.group(1).upper()}"
    
    # Realme devices
    realme_match = re.search(r'(realme [a-z0-9 ]+|rmx[0-9]+)', user_agent_lower)
    if realme_match:
        return f"Realme {realme_match.group(1).upper()}"
    
    # iPhone/iPad
    if 'iphone' in user_agent_lower:
        iphone_match = re.search(r'iphone[0-9,]+', user_agent_lower)
        if iphone_match:
            return iphone_match.group(0).replace(',', '.')
        return 'iPhone'
    
    if 'ipad' in user_agent_lower:
        return 'iPad'
    
    # Emulators
    if 'bluestacks' in user_agent_lower:
        return 'BlueStacks Emulator'
    if 'noxplayer' in user_agent_lower or 'nox' in user_agent_lower:
        return 'NoxPlayer Emulator'
    if 'memu' in user_agent_lower:
        return 'MEmu Emulator'
    if 'ldplayer' in user_agent_lower:
        return 'LDPlayer Emulator'
    if 'genymotion' in user_agent_lower:
        return 'Genymotion Emulator'
    
    # Generic Android
    if 'android' in user_agent_lower:
        android_match = re.search(r'android ([0-9.]+)', user_agent_lower)
        if android_match:
            return f"Android {android_match.group(1)}"
        return 'Android Device'
    
    # Windows
    if 'windows' in user_agent_lower:
        windows_match = re.search(r'windows nt ([0-9.]+)', user_agent_lower)
        if windows_match:
            version_map = {
                '10.0': 'Windows 10/11',
                '6.3': 'Windows 8.1',
                '6.2': 'Windows 8',
                '6.1': 'Windows 7',
            }
            nt_version = windows_match.group(1)
            return version_map.get(nt_version, f'Windows NT {nt_version}')
        return 'Windows PC'
    
    # macOS
    if 'macintosh' in user_agent_lower or 'mac os' in user_agent_lower:
        mac_match = re.search(r'mac os x ([0-9_]+)', user_agent_lower)
        if mac_match:
            version = mac_match.group(1).replace('_', '.')
            return f'macOS {version}'
        return 'Mac'
    
    # Linux
    if 'linux' in user_agent_lower:
        if 'ubuntu' in user_agent_lower:
            return 'Ubuntu Linux'
        elif 'fedora' in user_agent_lower:
            return 'Fedora Linux'
        elif 'debian' in user_agent_lower:
            return 'Debian Linux'
        return 'Linux'
    
    return 'Unknown Device'


def generate_device_fingerprint(
    ip_address: str,
    user_agent: str,
    headers: Optional[Dict[str, str]] = None
) -> str:
    """
    Generate a unique device fingerprint hash using SERVER-SIDE data only
    This is more secure as client cannot manipulate the fingerprint
    
    Args:
        ip_address: Client IP address
        user_agent: User agent string
        headers: HTTP request headers for additional fingerprinting:
            - Accept-Language: Browser language preferences
            - Accept-Encoding: Supported encoding types
            - Accept: Supported content types
            - DNT: Do Not Track setting
            - Sec-CH-UA: User agent client hints
            - Sec-CH-UA-Platform: Platform from client hints
            - Sec-CH-UA-Mobile: Mobile indicator from client hints
    
    Returns:
        SHA-256 hash as device fingerprint
    """
    # Combine server-side data for fingerprinting (secure, cannot be manipulated by client)
    fingerprint_components = [
        ip_address,
        user_agent
    ]
    
    # Add HTTP headers for enhanced fingerprinting (all server-side)
    if headers:
        # Priority headers that provide good fingerprinting data
        priority_headers = [
            'Accept-Language',
            'Accept-Encoding',
            'Accept',
            'DNT',
            'Sec-CH-UA',
            'Sec-CH-UA-Platform',
            'Sec-CH-UA-Mobile',
            'Sec-CH-UA-Full-Version',
            'Upgrade-Insecure-Requests',
            'Sec-Fetch-Site',
            'Sec-Fetch-Mode',
            'Sec-Fetch-Dest'
        ]
        
        for header in priority_headers:
            if header in headers and headers[header]:
                fingerprint_components.append(f"{header}:{headers[header]}")
    
    # Create hash
    fingerprint_string = '|'.join(fingerprint_components)
    fingerprint_hash = hashlib.sha256(fingerprint_string.encode('utf-8')).hexdigest()
    
    return fingerprint_hash


def validate_fingerprint_data(data: Dict[str, str]) -> Tuple[bool, str]:
    """
    Validate client-side fingerprint data for integrity and completeness
    
    Args:
        data: Fingerprint data from client
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Require minimum number of characteristics for reliable fingerprinting
    required_fields = ['canvas_fingerprint', 'screen_resolution', 'timezone', 'language']
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    
    if missing_fields:
        return False, f"Missing required fingerprint fields: {', '.join(missing_fields)}"
    
    # Validate data format
    if data.get('screen_resolution'):
        if 'x' not in str(data['screen_resolution']):
            return False, "Invalid screen resolution format"
    
    if data.get('canvas_fingerprint'):
        if len(str(data['canvas_fingerprint'])) < 10:
            return False, "Canvas fingerprint too short"
    
    # Check for obvious spoofing attempts (all values identical or sequential)
    values = [str(v) for v in data.values() if v]
    if len(set(values)) < 3:
        return False, "Suspicious fingerprint data detected"
    
    return True, ""


def generate_hardware_fingerprint(user_agent: str, headers: Optional[Dict[str, str]] = None) -> str:
    """
    Generate a hardware-specific fingerprint using SERVER-SIDE data only
    This fingerprint is more persistent across sessions but less unique than device fingerprint
    
    Args:
        user_agent: User agent string
        headers: HTTP request headers
    
    Returns:
        SHA-256 hash of hardware fingerprint
    """
    hardware_components = [
        user_agent
    ]
    
    # Use server-side headers that indicate hardware/platform characteristics
    if headers:
        hardware_headers = [
            'Sec-CH-UA',
            'Sec-CH-UA-Platform',
            'Sec-CH-UA-Mobile',
            'Sec-CH-UA-Full-Version',
            'Sec-CH-UA-Platform-Version',
            'Sec-CH-UA-Arch',
            'Sec-CH-UA-Model'
        ]
        
        for header in hardware_headers:
            if header in headers and headers[header]:
                hardware_components.append(f"{header}:{headers[header]}")
    
    hardware_string = '|'.join(hardware_components)
    hardware_hash = hashlib.sha256(hardware_string.encode('utf-8')).hexdigest()
    
    return hardware_hash


def is_likely_emulator(user_agent: str, device_name: str) -> bool:
    """Check if device is likely an emulator"""
    user_agent_lower = user_agent.lower()
    device_name_lower = device_name.lower()
    
    emulator_indicators = [
        'generic', 'sdk_gphone', 'emulator', 'virtualbox',
        'vmware', 'genymotion', 'bluestacks', 'noxplayer',
        'memu', 'ldplayer', 'vbox'
    ]
    
    for indicator in emulator_indicators:
        if indicator in user_agent_lower or indicator in device_name_lower:
            return True
    
    return False


def get_device_info_summary(device_data: Dict[str, Optional[str]]) -> str:
    """Generate a human-readable device info summary"""
    parts = []
    
    if device_data.get('device_name') and device_data['device_name'] != 'Unknown':
        parts.append(device_data['device_name'])
    elif device_data.get('device_type') and device_data['device_type'] != 'Unknown':
        parts.append(device_data['device_type'])
    
    if device_data.get('operating_system') and device_data['operating_system'] != 'Unknown':
        parts.append(device_data['operating_system'])
    
    if device_data.get('browser_name') and device_data['browser_name'] != 'Unknown':
        browser_info = str(device_data['browser_name'])
        if device_data.get('browser_version') and device_data['browser_version'] != 'Unknown':
            browser_info += f" {device_data['browser_version']}"
        parts.append(browser_info)
    
    return ' | '.join(parts) if parts else 'Unknown Device'
