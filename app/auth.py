"""
IC-Pi Platform: Authentication Utilities
==========================================
Provides:
- Password hashing and verification (bcrypt via passlib)
- JWT creation and decoding (python-jose)
- Magic-link token creation and decoding (SME access)

Used by: app/routes/auth.py

Environment variables required:
- SECRET_KEY: Used to sign JWTs (set in Railway)
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel


SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


class TokenData(BaseModel):
    user_id: str
    email: str
    role: str


def create_access_token(user_id: str, email: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        if user_id is None:
            return None
        return TokenData(user_id=user_id, email=email, role=role)
    except JWTError:
        return None


def create_magic_link_token(sme_id: str, discovery_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=7)
    payload = {
        "sme_id": sme_id,
        "discovery_id": discovery_id,
        "type": "magic_link",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_magic_link_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "magic_link":
            return None
        sme_id = payload.get("sme_id")
        discovery_id = payload.get("discovery_id")
        if not sme_id or not discovery_id:
            return None
        return {"sme_id": sme_id, "discovery_id": discovery_id}
    except JWTError:
        return None
