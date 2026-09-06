"""Pytest configuration and shared fixtures for Telephony testing."""

import hashlib
import hmac
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.main import app
from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)


@pytest.fixture
def mock_webhook_secret() -> str:
    """Provide a standard test secret for signing."""
    return "test_mock_webhook_secret_key_12345"


@pytest.fixture
def test_settings(mock_webhook_secret: str) -> TelephonySettings:
    """Return isolated TelephonySettings configured for testing."""
    return TelephonySettings(
        webhook_secret=SecretStr(mock_webhook_secret),
        signature_verification_enabled=True,
        webhook_tolerance_seconds=300,
        environment="test",
        voice_engine_enabled=False,
    )


@pytest.fixture
def client(test_settings: TelephonySettings) -> Generator[TestClient, None, None]:
    """TestClient configured with overridden settings."""
    app.dependency_overrides[get_telephony_settings] = lambda: test_settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sign_payload(mock_webhook_secret: str) -> Callable[[bytes, int | None], str]:
    """Helper fixture to compute HMAC-SHA256 signature for test payloads."""

    def _signer(payload_bytes: bytes, timestamp: int | None = None) -> str:
        if timestamp is not None:
            message = f"{timestamp}.".encode() + payload_bytes
        else:
            message = payload_bytes
        return hmac.new(
            mock_webhook_secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

    return _signer


@pytest.fixture
def valid_inbound_dict() -> dict:
    """Sample valid inbound call dictionary."""
    return {
        "call_sid": "call_test_12345678",
        "from_number": "+919876543210",
        "to_number": "+911140001234",
        "direction": "inbound",
        "call_status": "initiated",
        "custom_parameters": {"campaign_id": "summer_2026"},
    }
