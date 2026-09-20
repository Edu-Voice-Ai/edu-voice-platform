"""
Edu-Voice-Ai — Backend Test Fixtures & Mock Helpers
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import uuid4
import jwt
import pytest
from httpx import AsyncClient, ASGITransport

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.core.config import settings
from app.core.security import AuthenticatedUser
from app.dependencies.auth import get_current_user
from app.db.session import get_db


TEST_JWT_SECRET = "test_jwt_secret_for_unit_tests_32_bytes_long"
settings.SUPABASE_JWT_SECRET = TEST_JWT_SECRET


def create_test_jwt(
    user_id: str = str(uuid4()),
    email: str = "test@eduvoice.ai",
    role: str = "authenticated",
    expires_in_seconds: int = 3600,
) -> str:
    """Generates a valid Supabase-compatible JWT signed with TEST_JWT_SECRET."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "aud": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
        "user_metadata": {"full_name": "Test User", "avatar_url": "https://avatar.com/test"},
        "app_metadata": {"provider": "email"},
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


import pytest_asyncio

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provides an AsyncClient for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict:
    """Returns valid Authorization Bearer headers with a test user."""
    token = create_test_jwt()
    return {"Authorization": f"Bearer {token}"}
