from quart import redirect, session
from bot.database import AsyncSessionLocal
from bot.models import Publisher
from sqlalchemy import select
from functools import wraps

def require_publisher(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if 'publisher_id' not in session:
            return redirect('/login')
        
        async with AsyncSessionLocal() as db_session:
            result = await db_session.execute(
                select(Publisher).where(Publisher.id == session['publisher_id'])
            )
            publisher = result.scalar_one_or_none()
            
            if not publisher or not publisher.is_active:
                session.clear()
                return redirect('/login')
        
        return await func(*args, **kwargs)
    return wrapper
