from fastapi import Request, Depends
from app.core import get_current_user


# Dependency to get current authenticated user
async def get_current_user_dependency(request: Request) -> str:
    """
    Get current authenticated user from JWT token.
    This wraps the core security function for use in API routes.
    """
    return await get_current_user(request)


__all__ = ["get_current_user_dependency"]

