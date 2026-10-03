"""Integration unit tests for Telephony FastAPI router endpoints."""

import json

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)


def test_inbound_webhook_success(
    client: TestClient,
    valid_inbound_dict: dict,
    sign_payload,
) -> None:
    """Test successful inbound webhook processing with valid signature."""
    payload_bytes = json.dumps(valid_inbound_dict).encode("utf-8")
    sig = sign_payload(payload_bytes, None)

    response = client.post(
        "/api/v1/telephony/webhook",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Telephony-Signature": sig,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["call_sid"] == valid_inbound_dict["call_sid"]
    assert data["action"] == "process"


def test_inbound_webhook_invalid_signature_rejected(
    client: TestClient,
    valid_inbound_dict: dict,
) -> None:
    """Test webhook is rejected with 401 when signature is invalid."""
    payload_bytes = json.dumps(valid_inbound_dict).encode("utf-8")

    response = client.post(
        "/api/v1/telephony/webhook",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Telephony-Signature": "invalid_sig_hex_1234567890",
        },
    )

    assert response.status_code == 401
    assert "signature" in response.json()["detail"].lower()


def test_inbound_webhook_missing_signature_rejected(
    client: TestClient,
    valid_inbound_dict: dict,
) -> None:
    """Test webhook is rejected with 401 when signature header is omitted."""
    response = client.post(
        "/api/v1/telephony/webhook",
        json=valid_inbound_dict,
    )

    assert response.status_code == 401
    assert "signature" in response.json()["detail"].lower()


def test_inbound_webhook_invalid_payload_with_valid_signature(
    client: TestClient,
    sign_payload,
) -> None:
    """Test that a validly signed but malformed JSON body returns 422 Unprocessable Entity."""
    invalid_data = {"call_sid": "", "from_number": "+919999"}
    payload_bytes = json.dumps(invalid_data).encode("utf-8")
    sig = sign_payload(payload_bytes, None)

    response = client.post(
        "/api/v1/telephony/webhook",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Telephony-Signature": sig,
        },
    )

    assert response.status_code == 422


def test_inbound_webhook_verification_disabled_override(
    valid_inbound_dict: dict,
) -> None:
    """Test that requests pass without signature if verification is explicitly disabled in config."""
    disabled_settings = TelephonySettings(
        signature_verification_enabled=False,
        environment="test",
    )
    app.dependency_overrides[get_telephony_settings] = lambda: disabled_settings

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/telephony/webhook",
                json=valid_inbound_dict,
            )
            assert response.status_code == 200
            assert response.json()["status"] == "accepted"
    finally:
        app.dependency_overrides.clear()


def test_events_callback_success(
    client: TestClient,
    sign_payload,
) -> None:
    """Test call status event callback endpoint."""
    event_data = {
        "call_sid": "call_test_12345678",
        "event_type": "call_disconnected",
        "call_status": "completed",
        "duration_seconds": 60,
        "hangup_cause": "caller_hangup",
    }
    payload_bytes = json.dumps(event_data).encode("utf-8")
    sig = sign_payload(payload_bytes, None)

    response = client.post(
        "/api/v1/telephony/events",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Telephony-Signature": sig,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["action"] == "acknowledged"
