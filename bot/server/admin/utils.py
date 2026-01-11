from quart import redirect, session
import bcrypt
from functools import wraps

def require_admin(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if 'publisher_id' not in session:
            return redirect('/login')
        if not session.get('is_admin'):
            return redirect('/publisher/dashboard')
        return await func(*args, **kwargs)
    return wrapper

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
