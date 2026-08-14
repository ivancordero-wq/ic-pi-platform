IC-π™ Platform: Authentication Utilities
=========================================
Handles JWT token creation/validation and password hashing.

Used by:
- app/routes/auth.py (login + magic-link endpoints)
- Future middleware for protecting routes

Dependencies: python-jose[cryptography], passlib[bcrypt]
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration (loaded from environment variables on Railway)
# ---------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours default

# ---------------------------------------------------------------------------
# Password Hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password for storage."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT Token Management
# ---------------------------------------------------------------------------
class TokenData(BaseModel):
    """Decoded token payload."""
    user_id: str
    email: str
    role: str  # "super_admin", "consultant", "leadership", "sme"


def create_access_token(user_id: str, email: str, role: str,
                        expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a signed JWT token embedding user identity and role.

    Args:
        user_id: UUID string of the authenticated user.
        email: User's email (for display/logging).
        role: One of: super_admin, consultant, leadership, sme.
        expires_delta: Custom expiration. Defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[TokenData]:
    """
    Decode and validate a JWT token.

    Returns:
        TokenData if valid, None if expired or tampered.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(
            user_id=payload["sub"],
            email=payload["email"],
            role=payload["role"],
        )
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Magic Link Token (for SME access)
# ---------------------------------------------------------------------------
MAGIC_LINK_EXPIRE_HOURS = int(os.getenv("MAGIC_LINK_EXPIRE_HOURS", "72"))


def create_magic_link_token(sme_id: str, discovery_id: str) -> str:
    """
    Create a short-lived token for SME magic-link access.
    Binds the SME to a specific Discovery (no password needed).

    Args:
        sme_id: UUID of the SME record.
        discovery_id: UUID of the Discovery they're participating in.

    Returns:
        Encoded JWT string (to be embedded in magic-link URL).
    """
    expire = datetime.utcnow() + timedelta(hours=MAGIC_LINK_EXPIRE_HOURS)
    payload = {
        "sub": sme_id,
        "discovery_id": discovery_id,
        "role": "sme",
        "type": "magic_link",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_magic_link_token(token: str) -> Optional[dict]:
    """
    Decode a magic-link token.

    Returns:
        Dict with sme_id, discovery_id, role if valid. None otherwise.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "magic_link":
            return None
        return {
            "sme_id": payload["sub"],
            "discovery_id": payload["discovery_id"],
            "role": payload["role"],
        }
    except JWTError:
        return None
