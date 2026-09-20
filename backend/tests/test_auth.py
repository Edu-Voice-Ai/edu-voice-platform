"""
Edu-Voice-Ai — Authentication & JWT Verification Tests
"""

from uuid import uuid4
import pytest
from httpx import AsyncClient
from tests.conftest import create_test_jwt
from app.core.security import verify_supabase_jwt
from app.core.exceptions import UnauthorizedException


def test_verify_valid_jwt():
    """Verify that a properly signed Supabase JWT decodes into AuthenticatedUser."""
    user_id = str(uuid4())
    token = create_test_jwt(user_id=user_id, email="counselor@institution.edu")
    user = verify_supabase_jwt(token)
    assert user.id == user_id
    assert user.email == "counselor@institution.edu"
    assert user.role == "authenticated"


def test_verify_expired_jwt():
    """Verify that an expired JWT raises UnauthorizedException."""
    token = create_test_jwt(expires_in_seconds=-60)
    with pytest.raises(UnauthorizedException) as exc_info:
        verify_supabase_jwt(token)
    assert "expired" in str(exc_info.value.message).lower()


def test_verify_invalid_signature_jwt():
    """Verify that a token with invalid signature raises UnauthorizedException."""
    token = create_test_jwt()
    tampered_token = token[:-5] + "XXXXX"
    with pytest.raises(UnauthorizedException):
        verify_supabase_jwt(tampered_token)


@pytest.mark.asyncio
async def test_unauthenticated_request_to_protected_route(client: AsyncClient):
    """Test that accessing /api/v1/me without Authorization header returns 401."""
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_malformed_token_returns_401(client: AsyncClient):
    """Test that malformed Bearer token returns 401."""
    response = await client.get("/api/v1/me", headers={"Authorization": "Bearer not_a_valid_jwt"})
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"
