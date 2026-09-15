"""Pytest configuration and shared fixtures for Telephony testing."""

import hashlib
import hmac
from collections.abc import Callable, Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.api.v1.telephony import get_phone_assignment_resolver
from backend.app.main import app
from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.routing.phone_assignment import (
    InMemoryPhoneAssignmentResolver,
    PhoneAssignmentResult,
    ResolvedAgentConfig,
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
def test_phone_resolver() -> InMemoryPhoneAssignmentResolver:
    """In-memory resolver populated with valid test DIDs."""
    resolver = InMemoryPhoneAssignmentResolver()
    default_cfg = ResolvedAgentConfig(
        organization_id="org_test_institution",
        agent_id="agent_test_counselor",
        agent_name="Test Counselor",
        is_active=True,
    )
    for num in (
        "+912249360001",
        "02249360001",
        "022-493-60001",
        "+919613886363",
        "09613886363",
        "096-138-86363",
        "+919513886363",
        "09513886363",
        "095-138-86363",
        "+911140001234",
        "+918047361234",
        "+914045901132",
        "04045901132",
        "040-459-01132",
    ):
        resolver.register_assignment(
            PhoneAssignmentResult(
                phone_number=num,
                organization_id="org_test_institution",
                agent_id="agent_test_counselor",
                agent_type="admission_ai",
                is_active=True,
                agent_config=default_cfg,
            )
        )
    return resolver


@pytest.fixture
def client(
    test_settings: TelephonySettings,
    test_phone_resolver: InMemoryPhoneAssignmentResolver,
) -> Generator[TestClient, None, None]:
    """TestClient configured with overridden settings and test resolver."""
    app.dependency_overrides[get_telephony_settings] = lambda: test_settings
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: test_phone_resolver
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
