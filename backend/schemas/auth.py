"""
Authentication Domain Schemas
=============================
Defines the Pydantic models for session management and user identification.
"""

from pydantic import BaseModel


class MockLoginRequest(BaseModel):
    """
    Input schema for the JIT registration/login flow.
    """
    email: str
    role: str  # Must be 'submitter' or 'contributor'


class TokenResponse(BaseModel):
    """
    Standard JWT response returned upon successful authentication.
    """
    access_token: str
    token_type: str = "bearer"
    user: dict  # Contains id, email, and role
