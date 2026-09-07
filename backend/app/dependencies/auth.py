"""
Edu-Voice-Ai — Authentication Dependency Injections
Extracts Bearer token from headers and validates against Supabase Auth.
"""

from typing import Optional
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.exceptions import UnauthorizedException
from app.core.security import AuthenticatedUser, verify_supabase_jwt

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> AuthenticatedUser:
    """
    Extracts Bearer JWT from Authorization header and verifies it.
    Raises 401 UnauthorizedException if missing or invalid.
    """
    if not auth_header or not auth_header.credentials:
        raise UnauthorizedException("Authorization header is missing or malformed. Expected 'Bearer <token>'.")

    return verify_supabase_jwt(auth_header.credentials)


async def require_authenticated_user(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    """Explicit dependency ensuring the caller is an authenticated user."""
    if not current_user or not current_user.id:
        raise UnauthorizedException("Authenticated session is required.")
    return current_user


async def verify_internal_service_key(
    x_internal_service_key: Optional[str] = Header(None, alias="X-Internal-Service-Key"),
) -> bool:
    """
    Validates service-to-service authentication for internal endpoints (e.g. Telephony Voice Gateway).
    Enforces constant-time string comparison to prevent timing attacks.
    """
    import secrets
    from app.core.config import settings
    from app.core.exceptions import AppException
    from fastapi import status

    expected_key = settings.INTERNAL_SERVICE_KEY
    if not x_internal_service_key or not expected_key or not secrets.compare_digest(x_internal_service_key, expected_key):
        raise AppException(
            message="Invalid or missing X-Internal-Service-Key header.",
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED_INTERNAL_SERVICE",
        )
    return True
