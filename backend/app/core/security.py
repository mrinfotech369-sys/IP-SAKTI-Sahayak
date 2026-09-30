"""Password hashing and JWT session tokens."""
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"
SESSION_COOKIE = "ipsakti_session"

_PASSWORD_RULES = [
    (lambda p: len(p) >= 8, "at least 8 characters"),
    (lambda p: re.search(r"[A-Za-z]", p), "a letter"),
    (lambda p: re.search(r"\d", p), "a number"),
]


def password_problems(password: str) -> list[str]:
    return [msg for rule, msg in _PASSWORD_RULES if not rule(password)]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    token = jwt.encode({"sub": user_id, "exp": expires, "typ": "access"}, settings.JWT_SECRET, algorithm=ALGORITHM)
    return token, expires


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None
    return payload.get("sub")


def safe_client_id(ip: Optional[str]) -> Optional[str]:
    """One-way hash of the client IP so audit logs never store raw addresses."""
    if not ip:
        return None
    return hashlib.sha256((settings.SESSION_SECRET + ip).encode()).hexdigest()[:24]
