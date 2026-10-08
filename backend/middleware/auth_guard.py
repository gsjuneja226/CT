"""
Authentication & Authorization Guards
=====================================
Middleware components for securing FastAPI routes. Uses Dependency Injection 
to enforce identity verification across different platform actors (Users vs. Nodes).

Security Model:
- OAuth2PasswordBearer: Standard header parsing (Authorization: Bearer <token>).
- Identity Isolation: A User token cannot be used to heartbeat, and a 
  Node token cannot be used to submit new jobs.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from services.auth_service import decode_token
from database import fetchone

# Configures the standard header extraction for the Bearer token scheme.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/mock-login")


def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Validates that the requester is a registered human researcher or contributor.
    
    Logic:
    1. Decodes and verifies the JWT signature.
    2. Ensures the 'type' claim is 'user'.
    3. Retrieves the full user profile from the database.
    """
    payload = decode_token(token)
    if payload.get("type") == "node":
        raise HTTPException(status_code=403, detail="Node token not allowed for user-level operations")
        
    user = fetchone("SELECT * FROM users WHERE id=%s", (payload["sub"],))
    if not user:
        raise HTTPException(status_code=401, detail="User identity not found in database")
        
    return dict(user)


def get_node_from_token(token: str = Depends(oauth2_scheme)):
    """
    Validates that the requester is an authorized compute agent (Node).
    Primarily used for heartbeats and result uploads.
    
    Logic:
    1. Decodes and verifies the JWT signature.
    2. Ensures the 'type' claim is 'node'.
    3. Retrieves the hardware profile from the database.
    """
    payload = decode_token(token)
    if payload.get("type") != "node":
        raise HTTPException(status_code=403, detail="User token not allowed for node-level heartbeats")
        
    node = fetchone("SELECT * FROM nodes WHERE id=%s", (payload["sub"],))
    if not node:
        raise HTTPException(status_code=401, detail="Compute node registry not found")
        
    return dict(node)
