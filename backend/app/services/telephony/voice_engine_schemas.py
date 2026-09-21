"""Voice Engine Transport Contract Schemas (Contract v1.0).

Typed Pydantic models for bidirectional communication between the Yasin Voice Gateway
and Lokesh's downstream Voice Engine over WebSocket.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VoiceEngineEventType(str, Enum):
    """Event names defined by Voice Engine Transport Contract v1.0."""

    SESSION_START = "session.start"
    SESSION_READY = "session.ready"
    AUDIO_INPUT = "audio.input"
    AUDIO_OUTPUT = "audio.output"
    RESPONSE_CANCELLED = "response.cancelled"
    RESPONSE_END = "response.end"
    SESSION_END = "session.end"
    LEAD_EXTRACTED = "lead.extracted"
    CALL_SUMMARY = "call.summary"
    HUMAN_HANDOFF_REQUEST = "human_handoff.request"
    HANDOFF_REQUESTED = "handoff.requested"
    HANDOFF_ACKNOWLEDGED = "handoff.acknowledged"
    HANDOFF_FALLBACK = "handoff.fallback"
    HANDOFF_CANCELLED = "handoff.cancelled"
    ERROR = "error"


class VoiceEngineTemplateType(str, Enum):
    """The 10 multi-industry agent templates supported by Voice Engine."""

    EDUCATION = "education"
    APPOINTMENT_BOOKING = "appointment_booking"
    REAL_ESTATE = "real_estate"
    SALES_DISCOVERY = "sales_discovery"
    EMI_COLLECTION = "emi_collection"
    HEALTHCARE_RENEWAL = "healthcare_renewal"
    ECOMMERCE_CART = "ecommerce_cart"
    ORDER_DELIVERY = "order_delivery"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    CUSTOM = "custom"


# ==============================================================================
# Client → Voice Engine Request Schemas
# ==============================================================================


class SessionStartPayload(BaseModel):
    """session.start request sent by Telephony Adapter immediately upon connection."""

    model_config = ConfigDict(extra="ignore")

    event: str = Field(
        default=VoiceEngineEventType.SESSION_START.value,
        description="Must be session.start",
    )
    session_id: str | None = Field(
        default=None,
        description="Unique call/session identifier",
    )
    call_id: str | None = Field(
        default=None,
        description="Platform call record correlation identifier (Contract 5)",
    )
    organization_id: str | None = Field(
        default=None,
        description="Tenant/business identifier",
    )
    agent_id: str | None = Field(
        default=None,
        description="AI Agent identifier",
    )
    call_direction: str = Field(
        default="inbound",
        description="Call direction: inbound or outbound (Contract 5)",
    )
    language: str | None = Field(
        default="en-IN",
        description="Initial language (e.g. en-IN, hi-IN, te-IN)",
    )
    client_sample_rate: int = Field(
        default=16000,
        description="Sample rate of inbound/outbound audio (16000 or 8000)",
    )
    template_type: str = Field(
        default=VoiceEngineTemplateType.EDUCATION.value,
        description="Agent template type (defaults to education)",
    )
    business_name: str = Field(
        default="Apex University",
        description="Human-readable business name (defaults to Apex University)",
    )
    agent_name: str | None = Field(
        default=None,
        description="Persona/agent name override",
    )
    greeting_message: str | None = Field(
        default=None,
        description="Optional greeting message played immediately on start",
    )
    goodbye_message: str | None = Field(
        default=None,
        description="Optional goodbye message played on call end",
    )
    system_prompt: str | None = Field(
        default=None,
        description="Custom system prompt override (primarily for custom template)",
    )


class AudioInputJsonPayload(BaseModel):
    """audio.input JSON payload (Option B) for inbound caller audio frames."""

    event: str = Field(
        default=VoiceEngineEventType.AUDIO_INPUT.value,
        description="Must be audio.input",
    )
    data: str = Field(
        ...,
        description="Base64-encoded raw PCM16 audio bytes",
    )
    seq: int | None = Field(
        default=None,
        description="Optional monotonic packet sequence number",
    )


class SessionEndPayload(BaseModel):
    """session.end request sent by Telephony Adapter on call termination."""

    event: str = Field(
        default=VoiceEngineEventType.SESSION_END.value,
        description="Must be session.end",
    )
    session_id: str | None = Field(default=None, description="Unique session identifier")
    call_id: str | None = Field(default=None, description="Unique call identifier")
    reason: str = Field(
        default="normal_closure",
        description="Reason for termination, e.g. transferred_to_human, caller_hangup",
    )


class HandoffAcknowledgedPayload(BaseModel):
    """handoff.acknowledged frame sent by Gateway to Voice Engine upon accepting handoff."""

    model_config = ConfigDict(extra="ignore")

    event: str = Field(
        default=VoiceEngineEventType.HANDOFF_ACKNOWLEDGED.value,
        description="Must be handoff.acknowledged",
    )
    session_id: str | None = Field(default=None)
    call_id: str | None = Field(default=None)
    status: str = Field(default="resolving_target")
    hold_media: bool = Field(default=True)


class HandoffFallbackPayload(BaseModel):
    """handoff.fallback frame sent by Gateway to Voice Engine when handoff cannot complete."""

    model_config = ConfigDict(extra="ignore")

    event: str = Field(
        default=VoiceEngineEventType.HANDOFF_FALLBACK.value,
        description="Must be handoff.fallback",
    )
    session_id: str | None = Field(default=None)
    call_id: str | None = Field(default=None)
    reason: str = Field(default="NO_ELIGIBLE_STAFF")
    prompt_instruction: str | None = Field(
        default="Apologize politely that all admission counselors are busy on other calls. Offer to take a message or schedule a callback.",
    )


class HandoffCancelledPayload(BaseModel):
    """handoff.cancelled frame sent by Gateway to Voice Engine on caller hangup during transfer."""

    model_config = ConfigDict(extra="ignore")

    event: str = Field(
        default=VoiceEngineEventType.HANDOFF_CANCELLED.value,
        description="Must be handoff.cancelled",
    )
    session_id: str | None = Field(default=None)
    call_id: str | None = Field(default=None)
    reason: str | None = Field(default="caller_hung_up")


# ==============================================================================
# Voice Engine → Client Outbound Event Schemas
# ==============================================================================


class BaseVoiceEngineEvent(BaseModel):
    """Base envelope model for all events emitted by Voice Engine."""

    model_config = ConfigDict(extra="ignore")

    event: str = Field(..., description="Event type identifier")
    session_id: str | None = Field(default=None, description="Session identifier")
    turn_id: str | None = Field(default=None, description="Conversational turn identifier")
    generation_id: str | None = Field(default=None, description="Speech generation identifier")
    timestamp_ms: float | None = Field(default=None, description="Server timestamp in milliseconds")
    data: dict[str, Any] = Field(default_factory=dict, description="Event payload body")


class SessionReadyEvent(BaseVoiceEngineEvent):
    """session.ready event emitted when Voice Engine workers are initialized."""

    event: str = Field(default=VoiceEngineEventType.SESSION_READY.value)


class AudioOutputData(BaseModel):
    """Payload data embedded in audio.output event."""

    model_config = ConfigDict(extra="ignore")

    data: str = Field(..., description="Base64-encoded raw PCM16 audio chunk")
    seq: int | None = Field(default=None, description="Monotonic sequence number")
    sample_rate: int = Field(default=16000, description="Sampling rate in Hz (16000 or 8000)")
    duration_ms: float = Field(default=20.0, description="Audio frame duration in ms")
    language: str | None = Field(default=None, description="Spoken language tag")
    cancellation_cycle: int = Field(default=0, description="Cancellation generation index")


class AudioOutputEvent(BaseVoiceEngineEvent):
    """audio.output event delivering synthesized TTS audio chunks."""

    event: str = Field(default=VoiceEngineEventType.AUDIO_OUTPUT.value)
    data: dict[str, Any] = Field(default_factory=dict)

    def extract_audio_data(self) -> AudioOutputData:
        """Parse structured audio payload from data dictionary."""
        return AudioOutputData.model_validate(self.data)


class ResponseCancelledData(BaseModel):
    """Payload data embedded in response.cancelled barge-in event."""

    model_config = ConfigDict(extra="ignore")

    reason: str | None = Field(default=None, description="Interruption reason description")
    interrupted_at_ms: float | None = Field(default=None, description="Timestamp of interruption")


class ResponseCancelledEvent(BaseVoiceEngineEvent):
    """response.cancelled event emitted upon caller speech barge-in."""

    event: str = Field(default=VoiceEngineEventType.RESPONSE_CANCELLED.value)

    def extract_cancellation_data(self) -> ResponseCancelledData:
        """Parse structured cancellation payload."""
        return ResponseCancelledData.model_validate(self.data)


class ResponseEndData(BaseModel):
    """Payload data embedded in response.end event."""

    model_config = ConfigDict(extra="ignore")

    turn_id: str | None = Field(default=None, description="Completed turn ID")
    stt_latency_ms: float | None = Field(default=None, description="Speech-to-text latency in ms")
    llm_ttft_ms: float | None = Field(default=None, description="LLM time to first token in ms")
    tts_first_audio_ms: float | None = Field(default=None, description="TTS first audio latency in ms")
    total_speech_to_first_audio_ms: float | None = Field(
        default=None, description="End-to-end speech to audio latency in ms"
    )


class ResponseEndEvent(BaseVoiceEngineEvent):
    """response.end event emitted when an AI response finishes generating."""

    event: str = Field(default=VoiceEngineEventType.RESPONSE_END.value)

    def extract_latency_data(self) -> ResponseEndData:
        """Parse structured latency telemetry."""
        return ResponseEndData.model_validate(self.data)


class LeadExtractedEvent(BaseVoiceEngineEvent):
    """lead.extracted event delivering structured lead metadata post-call."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    event: str = Field(default=VoiceEngineEventType.LEAD_EXTRACTED.value)
    lead_payload: dict[str, Any] | None = Field(default=None, alias="lead")

    @property
    def lead(self) -> dict[str, Any]:
        """Convenience property to access lead object."""
        if self.lead_payload is not None:
            return self.lead_payload
        return self.data.get("lead", {}) if isinstance(self.data, dict) else {}


class CallSummaryEvent(BaseVoiceEngineEvent):
    """call.summary event delivering structured conversational summary post-call."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    event: str = Field(default=VoiceEngineEventType.CALL_SUMMARY.value)
    summary_payload: dict[str, Any] | None = Field(default=None, alias="summary")

    @property
    def summary(self) -> dict[str, Any]:
        """Convenience property to access summary object."""
        if self.summary_payload is not None:
            return self.summary_payload
        return self.data.get("summary", {}) if isinstance(self.data, dict) else {}


class HandoffRequestedEvent(BaseVoiceEngineEvent):
    """Canonical handoff.requested event emitted when AI determines real human forwarding is required."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    event: str = Field(default=VoiceEngineEventType.HANDOFF_REQUESTED.value)
    handoff_id: str | None = Field(default=None, description="Correlated handoff identifier")
    call_id: str | None = Field(default=None, description="Correlated call identifier")
    organization_id: str | None = Field(default=None, description="Tenant organization identifier")
    agent_id: str | None = Field(default=None, description="Assigned AI agent identifier")
    requested_role: str | None = Field(
        default="admission_counselor",
        description="Role requested for transfer (e.g. admission_counselor, accounts, warden)",
    )
    requested_department: str | None = Field(
        default="admissions",
        description="Department requested for transfer",
    )
    requested_staff_id: str | None = Field(
        default=None,
        alias="staff_id",
        description="Specific staff member ID requested if known",
    )
    caller_phone_number: str | None = Field(
        default=None,
        description="Caller's phone number",
    )
    reason: str | None = Field(
        default="caller_requested_human",
        description="Reason triggering human transfer (e.g. caller_requested_human, complex_query)",
    )
    confidence: float | None = Field(
        default=None,
        description="Confidence score of handoff intent detection (0.0 - 1.0)",
    )
    target_phone_number: str | None = Field(
        default=None,
        description="Legacy transfer number suggestion (ignored in favor of Backend resolution)",
    )


class HumanHandoffRequestEvent(HandoffRequestedEvent):
    """Backward-compatibility wrapper for legacy human_handoff.request event."""

    event: str = Field(default=VoiceEngineEventType.HUMAN_HANDOFF_REQUEST.value)


class VoiceEngineErrorEvent(BaseModel):
    """error event emitted on protocol or session errors."""

    model_config = ConfigDict(extra="ignore")

    event: str = Field(default=VoiceEngineEventType.ERROR.value)
    message: str = Field(default="Unknown Voice Engine error", description="Error description message")
    session_id: str | None = Field(default=None)
    data: dict[str, Any] = Field(default_factory=dict)
