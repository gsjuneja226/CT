"""
Authentication & JWT Identity Service
=====================================
Handles the generation and validation of JSON Web Tokens (JWT) using the 
HS256 symmetric algorithm.

Token Types:
- User Tokens: Short-lived (default 24hrs), used for dashboard access.
- Node Tokens: Long-lived (1 year), used by remote agents for 
  persistent grid connectivity.
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status
from config import settings


def create_token(payload: dict, expires_hours: Optional[int] = None) -> str:
    """
    Core utility to package a dictionary into a signed JWT string.
    """
    data = payload.copy()
    expire = datetime.utcnow() + timedelta(
        hours=expires_hours or settings.JWT_EXPIRY_HOURS
    )
    # The 'exp' claim is reserved for expiration timestamp
    data["exp"] = expire
    return jwt.encode(data, settings.JWT_SECRET, algorithm="HS256")


def create_user_token(user_id: str, email: str, role: str) -> str:
    """
    Generates a session token for a human researcher or contributor.
    Includes identity and role (submitter/contributor) in the payload.
    """
    return create_token({
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "user"
    })


def create_node_token(node_id: str) -> str:
    """
    Generates a high-persistence token for a compute node.
    Security Note: These tokens are valid for 1 year to prevent automated 
    agents from being locked out during long-running headless operations.
    """
    return create_token({
        "sub": node_id,
        "type": "node"
    }, expires_hours=24 * 365)


def decode_token(token: str) -> dict:
    """
    Validates a JWT against the project's secret key.
    
    Raises:
        HTTPException: 401 Unauthorized if the token is forged or expired.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
