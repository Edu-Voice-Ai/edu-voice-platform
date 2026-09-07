"""
Edu-Voice-Ai - Call, Transcript and Summary Schemas
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import Field
from app.schemas.common import BaseSchema

class CallTranscriptCreate(BaseSchema):
    speaker: str = Field(..., pattern="^(agent|caller|system)$")
    message: str = Field(..., min_length=1)
    language: Optional[str] = "en-IN"
    confidence: Optional[float] = None
    turn_index: int = 0
    audio_timestamp_offset_ms: Optional[int] = None
    latency_ms: Optional[int] = None

class CallTranscriptResponse(BaseSchema):
    id: UUID
    call_id: UUID
    organization_id: UUID
    speaker: str
    message: str
    language: Optional[str] = None
    confidence: Optional[float] = None
    turn_index: int
    audio_timestamp_offset_ms: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: datetime

class CallSummaryCreate(BaseSchema):
    summary: str = Field(..., min_length=5)
    sentiment: Optional[str] = Field(default="neutral", pattern="^(positive|neutral|negative|mixed)$")
    intent: Optional[str] = None
    key_topics: List[str] = []
    action_items: List[str] = []
    caller_satisfaction_score: Optional[int] = Field(default=None, ge=1, le=5)

class CallSummaryResponse(BaseSchema):
    id: UUID
    call_id: UUID
    organization_id: UUID
    summary: str
    sentiment: Optional[str] = None
    intent: Optional[str] = None
    key_topics: List[str] = []
    action_items: List[str] = []
    caller_satisfaction_score: Optional[int] = None
    created_at: datetime

class CallCreate(BaseSchema):
    caller_number: str = Field(..., min_length=10, max_length=20)
    receiver_number: str = Field(..., min_length=10, max_length=20)
    direction: str = Field(default="inbound", pattern="^(inbound|outbound)$")
    agent_id: Optional[UUID] = None
    phone_number_id: Optional[UUID] = None
    provider_call_id: Optional[str] = None
    metadata: Dict[str, Any] = {}

class CallUpdate(BaseSchema):
    status: Optional[str] = Field(None, pattern="^(queued|ringing|in_progress|completed|failed|busy|no_answer|canceled)$")
    started_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    recording_url: Optional[str] = None
    transferred_to_human: Optional[bool] = None
    transferred_to_phone: Optional[str] = None
    handoff_reason: Optional[str] = None
    handoff_at: Optional[datetime] = None
    disconnect_reason: Optional[str] = None
    language_detected: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class CallResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    agent_id: Optional[UUID] = None
    phone_number_id: Optional[UUID] = None
    provider_call_id: Optional[str] = None
    caller_number: str
    receiver_number: str
    direction: str
    status: str
    started_at: Optional[datetime] = None
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = 0
    recording_url: Optional[str] = None
    transferred_to_human: Optional[bool] = False
    transferred_to_phone: Optional[str] = None
    handoff_reason: Optional[str] = None
    handoff_at: Optional[datetime] = None
    disconnect_reason: Optional[str] = None
    language_detected: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class CallDetailResponse(CallResponse):
    metadata: Dict[str, Any] = {}
    transcripts: List[CallTranscriptResponse] = []
    summary: Optional[CallSummaryResponse] = None
