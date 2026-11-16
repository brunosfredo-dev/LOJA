import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timezone
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from .models import User, AuthThrottle

USERNAME = re.compile(r'^[a-z0-9_]{3,24}$')

def normalize_username(value):
    username = (value or '').strip().lower().lstrip('@')
    if not USERNAME.fullmatch(username):
        raise HTTPException(status_code=422, detail='Usuário deve ter 3 a 24 caracteres: letras minúsculas, números ou _.')
    return username

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return 'scrypt$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()

def verify_password(password, hashed):
    try:
        _, salt, expected = hashed.split('$')
        actual = hashlib.scrypt(password.encode('utf-8'), salt=base64.b64decode(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False

def require_user(request: Request, db: Session):
    uid = request.session.get('uid')
    user = db.get(User, uid) if isinstance(uid, int) else None
    if not user:
        raise HTTPException(status_code=401, detail='Entre na sua conta para continuar.')
    if request.session.get('sv') != user.session_version:
        raise HTTPException(status_code=401, detail='Sua sessão expirou. Entre novamente.')
    if user.is_banned:
        raise HTTPException(status_code=403, detail='Esta conta foi suspensa.')
    return user

def require_csrf(request: Request):
    token = request.headers.get('x-csrf-token', '')
    actual = request.session.get('csrf', '')
    if not actual or not hmac.compare_digest(token, actual):
        raise HTTPException(status_code=403, detail='Sessão expirada. Atualize a página e tente novamente.')

def issue_session(request, user):
    request.session.clear()
    request.session.update({'uid': user.id, 'sv': user.session_version, 'csrf': secrets.token_urlsafe(32)})

def throttle_check(request, db, username):
    ip = (request.client.host if request.client else 'unknown')[:120]
    key = hashlib.sha256((ip + ':' + username + ':' + os.getenv('THROTTLE_SALT', 'kritikus')).encode()).hexdigest()
    item = db.get(AuthThrottle, key)
    now = datetime.now(timezone.utc)
    if item:
        start = item.window_start.replace(tzinfo=timezone.utc) if item.window_start.tzinfo is None else item.window_start
        if (now - start).total_seconds() >= 900:
            item.attempts = 0
            item.window_start = now
        if item.attempts >= 12:
            raise HTTPException(status_code=429, detail='Muitas tentativas. Tente novamente mais tarde.')
    return key, item

def throttle_fail(db, key, item):
    if not item:
        item = AuthThrottle(key=key, attempts=0)
        db.add(item)
    item.attempts += 1
    db.commit()

def rate_limit(db, user_id: int, action: str, maximum: int, seconds: int = 900):
    """Small persistent fixed-window limiter shared by the Python service processes."""
    now = datetime.now(timezone.utc)
    key = hashlib.sha256(f'action:{action}:{user_id}'.encode()).hexdigest()
    item = db.get(AuthThrottle, key)
    if item is None:
        item = AuthThrottle(key=key, attempts=0, window_start=now)
        db.add(item)
    else:
        started = item.window_start.replace(tzinfo=timezone.utc) if item.window_start.tzinfo is None else item.window_start
        if (now - started).total_seconds() >= seconds:
            item.attempts = 0
            item.window_start = now
    if item.attempts >= maximum:
        raise HTTPException(429, 'Muitas ações em pouco tempo. Tente novamente mais tarde.')
    item.attempts += 1
    db.flush()
