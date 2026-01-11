from datetime import datetime, timedelta
from os import environ
import string
import secrets
import json
import urllib.parse
import httpx
from logging import getLogger

from bot.database import AsyncSessionLocal
from bot.models import Settings

logger = getLogger('uvicorn')


def generate_order_id(length=20):
    """Generate a random order ID"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


async def get_paytm_credentials():
    """Get Paytm credentials from database settings or environment variables"""
    async with AsyncSessionLocal() as db_session:
        from sqlalchemy import select
        result = await db_session.execute(select(Settings))
        settings = result.scalar_one_or_none()
        
        upi_id = (settings.paytm_upi_id if settings else None) or environ.get('PAYTM_UPI_ID')
        unit_id = (settings.paytm_unit_id if settings else None) or environ.get('PAYTM_UNIT_ID')
        paytm_signature = (settings.paytm_signature if settings else None) or environ.get('PAYTM_SIGNATURE')
        mid = (settings.paytm_mid if settings else None) or environ.get('PAYTM_MID')
        
        return {
            'upi_id': upi_id,
            'unit_id': unit_id,
            'signature': paytm_signature,
            'mid': mid
        }


async def create_payment_links(amount: float, order_id: str):
    """
    Create UPI payment links for a given amount and order ID.
    Returns dict with upi_link, qr_url, paytm_intent, and credentials.
    """
    credentials = await get_paytm_credentials()
    
    upi_id = credentials['upi_id']
    unit_id = credentials['unit_id']
    paytm_signature = credentials['signature']
    mid = credentials['mid']
    
    if not all([upi_id, unit_id]):
        return {
            'success': False,
            'error': 'Payment gateway not configured. Please contact administrator.'
        }
    
    upi_link = f"upi://pay?pa={upi_id}&am={amount}&pn={unit_id}&tn={order_id}&tr={order_id}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&ecc=H&margin=20&data={urllib.parse.quote(upi_link)}"
    
    if paytm_signature:
        paytm_intent = f"paytmmp://cash_wallet?pa={upi_id}&pn={unit_id}&am={amount}&cu=INR&tn={order_id}&tr={order_id}&mc=4722&sign={paytm_signature}&featuretype=money_transfer"
    else:
        paytm_intent = f"paytmmp://cash_wallet?pa={upi_id}&pn={unit_id}&am={amount}&cu=INR&tn={order_id}&tr={order_id}&mc=4722&featuretype=money_transfer"
    
    return {
        'success': True,
        'upi_link': upi_link,
        'qr_url': qr_url,
        'paytm_intent': paytm_intent,
        'upi_id': upi_id,
        'mid': mid
    }


async def check_paytm_status(order_id: str):
    """
    Check payment status from Paytm API.
    Returns dict with status, amount, utr, and success flag.
    """
    credentials = await get_paytm_credentials()
    mid = credentials['mid']
    
    if not mid:
        return {
            'success': False,
            'error': 'Payment verification not configured'
        }
    
    try:
        payload = json.dumps({'MID': mid, 'ORDERID': order_id})
        check_url = f"https://securegw.paytm.in/order/status?JsonData={urllib.parse.quote(payload)}"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                check_url,
                headers={"Content-Type": "application/json"}
            )
            response_data = response.json()
            
            logger.info(f"Payment status check for {order_id}: STATUS={response_data.get('STATUS')}")
            
            status = response_data.get('STATUS', '')
            txn_amount = response_data.get('TXNAMOUNT', '')
            utr = response_data.get('BANKTXNID', '')
            
            return {
                'success': True,
                'status': status,
                'amount': txn_amount,
                'utr': utr,
                'raw_response': response_data
            }
            
    except httpx.TimeoutException:
        logger.error(f"Timeout while checking payment status for {order_id}")
        return {
            'success': False,
            'error': 'Payment status check timed out'
        }
    except Exception as e:
        logger.error(f"Error checking payment status for {order_id}: {str(e)}")
        return {
            'success': False,
            'error': 'An error occurred while checking payment status'
        }


def calculate_expiry_date(duration_days: int, from_date: datetime | None = None) -> datetime:
    """Calculate subscription expiry date from a given date"""
    if from_date is None:
        from_date = datetime.utcnow()
    return from_date + timedelta(days=duration_days)
