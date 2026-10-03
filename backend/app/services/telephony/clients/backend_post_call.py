"""Post-Call Session Recording and Webhook Interface.

PENDING CONTRACT:
The server-side implementation of these endpoints in Aravind's FastAPI backend
is currently PENDING. This module provides only the client-side typed models
and interface definition to be activated once Aravind exposes the endpoints.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class CallSessionCreatePayload(BaseModel):
    """Payload to register an initiated or active call session."""

    call_id: str = Field(..., description="Unique call identifier")
    phone_number: str = Field(..., description="Dialed DID")
    caller_number: str | None = Field(
        default=None, description="Originating caller phone number"
    )
    agent_id: str = Field(..., description="Assigned agent UUID")
    direction: str = Field(default="inbound", description="Call direction")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Session metadata"
    )


class TranscriptChunkPayload(BaseModel):
    """Payload to append a conversational transcript turn."""

    call_id: str = Field(..., description="Call identifier")
    speaker: str = Field(
        ..., description="Speaker identity ('user', 'assistant', 'system')"
    )
    text: str = Field(..., description="Transcribed or synthesized speech text")
    timestamp_ms: int = Field(
        default=0, description="Offset in milliseconds from call start"
    )
    confidence: float | None = Field(default=None, description="STT confidence score")


class CallSummaryPayload(BaseModel):
    """Payload to append post-call AI summary and extracted lead fields."""

    call_id: str = Field(..., description="Call identifier")
    summary: str = Field(..., description="Concise conversational summary")
    sentiment: str | None = Field(default=None, description="Analyzed caller sentiment")
    lead_score: int | None = Field(
        default=None, description="Extracted admission lead quality score"
    )
    key_topics: list[str] = Field(
        default_factory=list, description="Primary discussion topics"
    )


class CallSessionUpdatePayload(BaseModel):
    """Payload to update final call duration, status, and recording URL."""

    status: str = Field(
        default="completed",
        description="Final call status ('completed', 'failed', 'transferred')",
    )
    duration_seconds: int = Field(
        default=0, description="Total call duration in seconds"
    )
    recording_url: str | None = Field(
        default=None, description="Audio recording S3 URL if enabled"
    )
    hangup_cause: str | None = Field(default=None, description="Termination reason")


class BaseBackendPostCallClient(ABC):
    """Abstract interface for reporting post-call data to Aravind's FastAPI backend."""

    @abstractmethod
    async def register_call(
        self,
        organization_id: str,
        payload: CallSessionCreatePayload,
    ) -> bool:
        """POST /api/v1/organizations/{organization_id}/calls"""

    @abstractmethod
    async def append_transcript(
        self,
        organization_id: str,
        call_id: str,
        payload: TranscriptChunkPayload,
    ) -> bool:
        """POST /api/v1/organizations/{organization_id}/calls/{call_id}/transcripts"""

    @abstractmethod
    async def save_summary(
        self,
        organization_id: str,
        call_id: str,
        payload: CallSummaryPayload,
    ) -> bool:
        """POST /api/v1/organizations/{organization_id}/calls/{call_id}/summary"""

    @abstractmethod
    async def finalize_call(
        self,
        organization_id: str,
        call_id: str,
        payload: CallSessionUpdatePayload,
    ) -> bool:
        """PATCH /api/v1/organizations/{organization_id}/calls/{call_id}"""
