"""Pydantic schemas and models for Telephony / Voice Gateway.

Contracts are typed and validated for provider-neutral telephony operation.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CallDirection(str, Enum):
    """Call direction enum."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(str, Enum):
    """Standardized telephony call status enum."""

    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    CANCELED = "canceled"


class CallEventType(str, Enum):
    """Telephony lifecycle event types."""

    CALL_INITIATED = "call_initiated"
    CALL_CONNECTED = "call_connected"
    CALL_DISCONNECTED = "call_disconnected"
    CALL_FAILED = "call_failed"
    STATUS_UPDATE = "status_update"


class InboundCallPayload(BaseModel):
    """Normalized payload model for incoming inbound call webhooks.

    Validates core fields required for intake, tenant routing, and session creation.
    """

    call_sid: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique provider-assigned call session identifier",
    )
    from_number: str = Field(
        ...,
        min_length=3,
        max_length=32,
        description="Caller's phone number (E.164 or national format)",
    )
    to_number: str = Field(
        ...,
        min_length=3,
        max_length=32,
        description="Dialed inbound DID number belonging to the institution/tenant",
    )
    direction: CallDirection = Field(
        default=CallDirection.INBOUND,
        description="Direction of the call",
    )
    call_status: CallStatus = Field(
        default=CallStatus.INITIATED,
        description="Current state of the call reported by the telephony provider",
    )
    timestamp: datetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the event in UTC",
    )
    custom_parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Generic extensible container for provider-specific attributes (Pending Contract)",
    )

    @field_validator("from_number", "to_number")
    @classmethod
    def validate_phone_not_empty(cls, v: str) -> str:
        """Validate phone numbers have stripped non-empty content."""
        clean = v.strip()
        if not clean:
            raise ValueError("Phone number cannot be blank")
        return clean

    @field_validator("call_sid")
    @classmethod
    def validate_call_sid(cls, v: str) -> str:
        """Validate call_sid is not whitespace."""
        clean = v.strip()
        if not clean:
            raise ValueError("Call SID cannot be blank")
        return clean


class CallStatusEventPayload(BaseModel):
    """Payload model for asynchronous call status/event callback notifications."""

    call_sid: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Provider-assigned call session identifier",
    )
    event_type: CallEventType = Field(
        ...,
        description="Type of lifecycle event being reported",
    )
    call_status: CallStatus = Field(
        ...,
        description="Updated call status",
    )
    duration_seconds: int | None = Field(
        default=None,
        ge=0,
        description="Duration of the call in seconds, if completed",
    )
    hangup_cause: str | None = Field(
        default=None,
        description="Reason for disconnect/hangup if available",
    )
    recording_url: str | None = Field(
        default=None,
        description="URL of call recording if generated (Pending Contract)",
    )
    timestamp: datetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the event in UTC",
    )


class TelephonyWebhookResponse(BaseModel):
    """Standardized HTTP response for accepted webhook intake."""

    status: str = Field(
        default="accepted",
        description="Acknowledgment status",
    )
    call_sid: str = Field(
        ...,
        description="Call session identifier associated with this response",
    )
    action: str = Field(
        default="process",
        description="Directive action returned to the provider (e.g. process, stream, reject)",
    )
    message: str = Field(
        default="Webhook received and queued for processing",
        description="Human-readable processing summary",
    )


class HealthResponse(BaseModel):
    """Application process health response."""

    status: str = Field(default="ok")
    service: str = Field(default="edu-voice-ai-backend")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    environment: str = Field(default="development")
