"""
Edu-Voice-Ai — Health & Readiness Endpoint Tests
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    """Test root metadata endpoint."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "Edu-Voice-Ai"
    assert data["docs"] == "/docs"


@pytest.mark.asyncio
async def test_root_health_endpoint(client: AsyncClient):
    """Test top-level /health liveness probe."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "edu-voice-backend"


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test /api/v1/health liveness probe."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "edu-voice-backend"
    assert "environment" in data


@pytest.mark.asyncio
async def test_readiness_endpoint(client: AsyncClient):
    """Test /api/v1/health/ready readiness probe."""
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "details" in data
