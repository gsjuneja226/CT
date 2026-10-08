"""
Role-Based Access Control (RBAC) Middleware
===========================================
Defines granular permission guards for API endpoints.
Enables fine-grained control over who can submit jobs vs. manage compute nodes.
"""

from fastapi import Depends, HTTPException
from middleware.auth_guard import get_current_user


def require_role(*roles):
    """
    Factory function that returns a dependency checker for specific user roles.
    
    Usage: 
    @app.post("/", user=Depends(require_role("submitter")))
    """
    def checker(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            # Rejection: The authenticated user possesses an incorrect role
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied. Role '{user['role']}' is insufficient. Required: {list(roles)}"
            )
        return user
        
    return checker
