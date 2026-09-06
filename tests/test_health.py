"""Unit tests for application health check endpoint."""

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    """Test GET /health returns 200 OK with expected status schema."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "edu-voice-ai-backend"
    assert "timestamp" in data
