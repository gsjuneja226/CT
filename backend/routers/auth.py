"""
Authentication & Identity Router
================================
Manages user sessions and identity registration. 

Design Note: 
Currently implements a 'Mock Login' strategy to facilitate easy onboarding 
within the campus network. It performs a Just-In-Time (JIT) registration 
of users upon their first login attempt.
"""

from fastapi import APIRouter, HTTPException
from schemas.auth import MockLoginRequest, TokenResponse
from services.auth_service import create_user_token
from database import fetchone, fetchone_returning

router = APIRouter()


@router.post("/mock-login", response_model=TokenResponse)
def mock_login(body: MockLoginRequest):
    """
    Handles user entry by verifying role and issuing a JWT.
    If the email is new, a record is created in the 'users' table.
    - Simulates a user login. 
    - Creates a new user record or updates the role of an existing user based 
    - on their email. Returns a JWT access token.
    """
    # Validation: enforce allowed roles
    if body.role not in ("submitter", "contributor"):
        raise HTTPException(status_code=400, detail="Role must be submitter or contributor")

    # JIT Registration / UPSERT Logic:
    # Ensures the user exists and has the correct role in the system.
    user = fetchone_returning("""
        INSERT INTO users (email, role)
        VALUES (%s, %s)
        ON CONFLICT (email) DO UPDATE SET role=EXCLUDED.role
        RETURNING *
    """, (body.email, body.role))

    if not user:
        raise HTTPException(status_code=500, detail="Failed to create/update user registry")

    # Convert RealDictRow to standard Python dictionary
    user = dict(user)
    
    # Generate the cryptographic identity token
    token = create_user_token(str(user["id"]), user["email"], user["role"])

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={"id": str(user["id"]), "email": user["email"], "role": user["role"]}
    )
