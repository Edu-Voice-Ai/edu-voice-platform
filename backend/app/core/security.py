"""
Edu-Voice-Ai — Security & JWT Verification Layer
Handles Supabase Auth JWT verification, claims extraction, and user identity resolution.
"""

from typing import Any, Dict, Optional
import jwt
from pydantic import BaseModel
from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.core.logging import logger


class AuthenticatedUser(BaseModel):
    """Represents the authenticated Supabase user extracted from a valid JWT."""
    id: str  # UUID as string
    email: str
    role: str = "authenticated"
    app_metadata: Dict[str, Any] = {}
    user_metadata: Dict[str, Any] = {}


def verify_supabase_jwt(token: str) -> AuthenticatedUser:
    """
    Decodes and verifies a Supabase Auth access token.
    Raises UnauthorizedException on invalid, expired, or malformed tokens.
    """
    if not token:
        raise UnauthorizedException("Authorization token is missing.")

    try:
        # Check if secret is configured with a real value
        jwt_secret = settings.SUPABASE_JWT_SECRET
        verify_signature = bool(jwt_secret and jwt_secret != "placeholder_jwt_secret")

        if verify_signature:
            # Full cryptographic HS256 signature verification
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": True, "verify_aud": False},
            )
        else:
            # Fallback for dev / mock mode with unverified signature, but still validating expiration
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": True},
            )

        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedException("Invalid token: missing subject (sub) claim.")

        email = payload.get("email") or payload.get("user_metadata", {}).get("email", "")

        return AuthenticatedUser(
            id=str(user_id),
            email=str(email),
            role=str(payload.get("role", "authenticated")),
            app_metadata=payload.get("app_metadata", {}),
            user_metadata=payload.get("user_metadata", {}),
        )

    except jwt.ExpiredSignatureError:
        logger.warning("Supabase JWT token has expired.")
        raise UnauthorizedException("Session has expired. Please log in again.")
    except jwt.InvalidTokenError as exc:
        logger.warning(f"Invalid Supabase JWT token: {str(exc)}")
        raise UnauthorizedException("Invalid authentication token.")
    except Exception as exc:
        logger.error(f"Unexpected token verification failure: {str(exc)}")
        raise UnauthorizedException("Authentication failed.")
