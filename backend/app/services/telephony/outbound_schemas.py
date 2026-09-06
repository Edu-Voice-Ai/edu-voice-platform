"""Pydantic schemas for Outbound Telephony Integration.

Implements Frozen V1 Contracts:
- Contract 1: Backend → Yasin Outbound API
- Contract 2: Outbound Job/Call ID & Idempotency
- Contract 3: Authorized Outbound Caller-ID Selection
- Contract 4: Outbound Call Status / State Machine
- Contract 5: Outbound Session Metadata
"""

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OutboundCallStatus(str, Enum):
    """Canonical outbound call lifecycle statuses defined in Contract 4."""

    QUEUED = "QUEUED"
    DIALING = "DIALING"
    RINGING = "RINGING"
    ANSWERED = "ANSWERED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    NO_ANSWER = "NO_ANSWER"
    BUSY = "BUSY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @classmethod
    def is_terminal(cls, status: "OutboundCallStatus | str") -> bool:
        """Check if status is a terminal state."""
        val = status.value if isinstance(status, OutboundCallStatus) else str(status)
        return val in {
            cls.COMPLETED.value,
            cls.NO_ANSWER.value,
            cls.BUSY.value,
            cls.FAILED.value,
            cls.CANCELLED.value,
        }


E164_REGEX = re.compile(r"^\+[1-9]\d{1,14}$")


class OutboundCallRequest(BaseModel):
    """Request schema for Backend → Yasin Outbound Call API (Contract 1)."""

    outbound_job_id: str = Field(
        ...,
        min_length=1,
        description="Unique dispatch attempt identifier from Backend (also Idempotency-Key)",
    )
    call_id: str = Field(
        ...,
        min_length=1,
        description="Platform call record correlation identifier",
    )
    organization_id: str = Field(
        ...,
        min_length=1,
        description="Tenant organization identifier",
    )
    campaign_id: str = Field(
        ...,
        min_length=1,
        description="Campaign identifier",
    )
    contact_id: str = Field(
        ...,
        min_length=1,
        description="Contact identifier",
    )
    agent_id: str = Field(
        ...,
        min_length=1,
        description="AI Agent identifier",
    )
    from_phone_number: str = Field(
        ...,
        min_length=3,
        description="Backend-authorized caller ID number (E.164 format)",
    )
    to_phone_number: str = Field(
        ...,
        min_length=3,
        description="Customer destination phone number (E.164 format)",
    )
    language: str = Field(
        default="en-IN",
        description="Runtime language code (e.g. en-IN, hi-IN)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Non-provider-specific contextual metadata",
    )

    @field_validator("from_phone_number", "to_phone_number")
    @classmethod
    def validate_e164_phone_format(cls, v: str) -> str:
        clean = v.strip().replace(" ", "").replace("-", "")
        if not clean.startswith("+"):
            clean = f"+{clean}"
        if not E164_REGEX.match(clean):
            raise ValueError(f"Phone number '{v}' is not a valid E.164 phone number format")
        return clean


class OutboundCallResponse(BaseModel):
    """Response schema for Backend → Yasin Outbound Call API (Contract 1)."""

    accepted: bool = Field(default=True, description="Whether the call was accepted for dialing")
    outbound_job_id: str = Field(..., description="Unique dispatch attempt identifier")
    call_id: str = Field(..., description="Platform call correlation identifier")
    gateway_call_id: str = Field(..., description="Gateway runtime call identifier")
    provider_call_id: str | None = Field(default=None, description="Telecom provider call identifier")
    status: OutboundCallStatus = Field(default=OutboundCallStatus.DIALING, description="Current call status")


class OutboundCallStatusCallbackPayload(BaseModel):
    """Payload sent by Gateway to Backend status callback endpoint (Contract 4)."""

    call_id: str = Field(..., description="Platform call record correlation identifier")
    outbound_job_id: str = Field(..., description="Unique dispatch attempt identifier")
    gateway_call_id: str = Field(..., description="Gateway runtime call identifier")
    provider_call_id: str | None = Field(default=None, description="Telecom provider call identifier")
    status: OutboundCallStatus = Field(..., description="Canonical call status")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the event in UTC",
    )
    failure_code: str | None = Field(default=None, description="Error or failure code if failed")
    failure_reason: str | None = Field(default=None, description="Human-readable reason if failed")
