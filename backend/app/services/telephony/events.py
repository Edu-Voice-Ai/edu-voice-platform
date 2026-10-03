"""Internal Normalized Telephony Event Models.

Defines provider-agnostic telephony lifecycle events (CALL_CONNECTED, START,
MEDIA, DTMF, MARK, CLEAR, STOP) required by the Voice Gateway architecture.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.frames import AudioFrame


class TelephonyEventType(str, Enum):
    """Normalized telephony lifecycle event types."""

    CALL_CONNECTED = "CALL_CONNECTED"
    START = "START"
    MEDIA = "MEDIA"
    DTMF = "DTMF"
    MARK = "MARK"
    CLEAR = "CLEAR"
    STOP = "STOP"


class NormalizedTelephonyEvent(BaseModel):
    """Provider-neutral event container ingested by the Voice Gateway."""

    event_type: TelephonyEventType = Field(
        ...,
        description="Standardized event classification",
    )
    call_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique telecom provider call identifier",
    )
    session_id: str | None = Field(
        default=None,
        description="Internal realtime gateway session identifier",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event creation timestamp in UTC",
    )
    organization_id: str | None = Field(
        default=None,
        description="Resolved tenant organization identifier",
    )
    agent_id: str | None = Field(
        default=None,
        description="Assigned AI agent identifier",
    )
    from_number: str | None = Field(
        default=None,
        description="Caller phone number (E.164)",
    )
    to_number: str | None = Field(
        default=None,
        description="Destination dialed DID number",
    )
    payload: bytes | None = Field(
        default=None,
        description="Raw audio payload bytes for MEDIA events",
    )
    sequence_number: int | None = Field(
        default=None,
        ge=0,
        description="Packet sequence index for streaming media",
    )
    timestamp_ms: int | None = Field(
        default=None,
        ge=0,
        description="Stream timestamp offset in milliseconds",
    )
    dtmf_digit: str | None = Field(
        default=None,
        description="Captured DTMF tone/digit (0-9, *, #, A-D)",
    )
    mark_name: str | None = Field(
        default=None,
        description="Label identifier for MARK synchronization events",
    )
    stop_reason: str | None = Field(
        default=None,
        description="Termination reason code for STOP events",
    )
    provider_name: str = Field(
        default="generic",
        description="Originating telephony provider adapter name",
    )
    provider_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Isolated provider-specific attributes (Pending Contract)",
    )

    @field_validator("call_id")
    @classmethod
    def validate_call_id(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("call_id cannot be blank")
        return clean

    @field_validator("dtmf_digit")
    @classmethod
    def validate_dtmf(cls, v: str | None) -> str | None:
        if v is not None:
            clean = v.strip().upper()
            valid_digits = set("0123456789*#ABCD")
            if not clean or any(c not in valid_digits for c in clean):
                raise ValueError(f"Invalid DTMF digit: '{v}'")
            return clean
        return None

    def to_audio_frame(self) -> AudioFrame:
        """Convert MEDIA event payload to internal AudioFrame."""
        if self.event_type != TelephonyEventType.MEDIA or self.payload is None:
            raise GatewayError(
                code=GatewayErrorCode.INVALID_FRAME_TYPE,
                message=f"Cannot extract AudioFrame from non-MEDIA event: {self.event_type}",
            )
        return AudioFrame(
            data=self.payload,
            sequence_number=self.sequence_number or 0,
            timestamp_ms=self.timestamp_ms or 0,
            metadata=self.provider_metadata,
        )
