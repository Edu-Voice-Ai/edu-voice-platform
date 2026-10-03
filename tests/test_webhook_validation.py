"""Unit tests for telephony payload validation schemas."""

import pytest
from pydantic import ValidationError

from backend.app.services.telephony.schemas import (
    CallDirection,
    CallEventType,
    CallStatus,
    CallStatusEventPayload,
    InboundCallPayload,
)


def test_valid_inbound_payload(valid_inbound_dict: dict) -> None:
    """Test valid inbound call payload deserialization and defaults."""
    payload = InboundCallPayload.model_validate(valid_inbound_dict)
    assert payload.call_sid == "call_test_12345678"
    assert payload.from_number == "+919876543210"
    assert payload.to_number == "+911140001234"
    assert payload.direction == CallDirection.INBOUND
    assert payload.call_status == CallStatus.INITIATED
    assert payload.custom_parameters["campaign_id"] == "summer_2026"
    assert payload.timestamp is not None


def test_missing_required_fields_inbound() -> None:
    """Test validation fails when required fields are missing."""
    with pytest.raises(ValidationError) as exc_info:
        InboundCallPayload.model_validate({})

    errors = exc_info.value.errors()
    missing_fields = {e["loc"][0] for e in errors}
    assert "call_sid" in missing_fields
    assert "from_number" in missing_fields
    assert "to_number" in missing_fields


def test_empty_or_whitespace_fields_inbound() -> None:
    """Test validation rejects blank or whitespace-only strings."""
    with pytest.raises(ValidationError):
        InboundCallPayload.model_validate(
            {
                "call_sid": "   ",
                "from_number": "+919876543210",
                "to_number": "+911140001234",
            }
        )

    with pytest.raises(ValidationError):
        InboundCallPayload.model_validate(
            {
                "call_sid": "call_123",
                "from_number": "",
                "to_number": "+911140001234",
            }
        )


def test_invalid_direction_or_status_enum() -> None:
    """Test invalid enum values are rejected."""
    with pytest.raises(ValidationError):
        InboundCallPayload.model_validate(
            {
                "call_sid": "call_123",
                "from_number": "+919876543210",
                "to_number": "+911140001234",
                "direction": "diagonal_invalid",
            }
        )


def test_valid_call_status_event_payload() -> None:
    """Test valid lifecycle status event payload."""
    event_dict = {
        "call_sid": "call_test_12345678",
        "event_type": "call_disconnected",
        "call_status": "completed",
        "duration_seconds": 45,
        "hangup_cause": "normal_clearing",
    }
    payload = CallStatusEventPayload.model_validate(event_dict)
    assert payload.call_sid == "call_test_12345678"
    assert payload.event_type == CallEventType.CALL_DISCONNECTED
    assert payload.call_status == CallStatus.COMPLETED
    assert payload.duration_seconds == 45
    assert payload.hangup_cause == "normal_clearing"


def test_invalid_event_payload_negative_duration() -> None:
    """Test negative duration_seconds is rejected."""
    with pytest.raises(ValidationError):
        CallStatusEventPayload.model_validate(
            {
                "call_sid": "call_test_123",
                "event_type": "call_disconnected",
                "call_status": "completed",
                "duration_seconds": -10,
            }
        )
