"""
Edu-Voice-Ai — Voice Engine Client Service Boundary Tests
"""

import pytest
from app.services.voice_engine import VoiceEngineClient


@pytest.mark.asyncio
async def test_voice_engine_client_headers():
    """Verify that client formats authentication headers properly."""
    client = VoiceEngineClient(
        base_url="http://localhost:8001",
        api_key="secret_voice_key_123",
        timeout_seconds=5,
    )
    headers = client._get_headers()
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Voice-Engine-Key"] == "secret_voice_key_123"


@pytest.mark.asyncio
async def test_voice_engine_unreachable_graceful_handling():
    """Verify that unreachable Voice Engine does not crash the server."""
    client = VoiceEngineClient(
        base_url="http://127.0.0.1:59999",  # non-existent port
        api_key="test_key",
        timeout_seconds=1,
    )
    health = await client.check_health()
    assert health["status"] == "unreachable"
